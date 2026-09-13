"""Списки: ordered/unordered, вложенные до 4 уровней.

Реализация — inline-маркер: каждый item превращается в обычный параграф со
``«маркер»\\t«текст»`` и висячим отступом. Стилевая автонумерация Word
заглушается явным ``<w:numId w:val="0"/>`` на уровне параграфа.

Inline-маркеры дают стабильный PDF без зависимости от того, как конкретный
рендерер (LibreOffice/Word) интерпретирует ``numbering.xml``.
"""

from __future__ import annotations

from collections.abc import Generator
from copy import copy
from typing import Any

from docx.shared import Length

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable
from markdown_gost.renderable.paragraph import Paragraph

from ._oxml import create_element

_MAX_LEVEL = 4

# Разделитель уровней для иерархической нумерации (`1.2.3.`). Захардкожен —
# по ГОСТ это всегда точка, конфигурировать незачем.
_HIERARCHICAL_SEPARATOR = "."

# Алфавиты для буквенной нумерации. Русский ГОСТ 7.32-2017 исключает
# ``ё, з, й, о, ч, ъ, ы, ь``.
_ALPHABETS_BY_STYLE: dict[str, str] = {
    "lower-alpha-ru": "абвгдежиклмнпрстуфхцшщэюя",
    "upper-alpha-ru": "АБВГДЕЖИКЛМНПРСТУФХЦШЩЭЮЯ",
    "lower-alpha-en": "abcdefghijklmnopqrstuvwxyz",
    "upper-alpha-en": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
}


class List(Renderable):
    """Контейнер для пунктов списка с поддержкой вложенности."""

    def __init__(
        self,
        parent: Any,
        config: Config,
        node: ast.List,
        *,
        bibliography: BibliographyIndex | None = None,
    ) -> None:
        self._parent = parent
        self._config = config
        self._bibliography = bibliography
        self._spec = config.lists
        self._indent_left = parse_length(self._spec.indent_left)
        self._indent_per_level = parse_length(self._spec.indent_per_level)

        self._paragraphs: list[Paragraph] = []
        self._build(
            node,
            level=1,
            start=node.start if node.ordered else 1,
            parent_path=[],
        )

    def _build(
        self,
        node: ast.List,
        *,
        level: int,
        start: int,
        parent_path: list[int] | None,
    ) -> None:
        clamped_level = min(level, _MAX_LEVEL)
        counter = start
        marker_style = _resolve_marker_style(node)
        delimiter = node.delimiter if marker_style == "arabic" else None
        for item in node.items:
            # ``parent_path is None`` означает, что цепочка arabic-предков прервана
            # (был bullet/alpha) — иерархическую нумерацию не строим.
            if marker_style == "arabic" and parent_path is not None:
                full_path: list[int] | None = [*parent_path, counter]
            else:
                full_path = None
            blocks = _item_blocks(item)
            has_para = any(kind == "para" for kind, _ in blocks)
            # Пустой wrapper-item (например, пропущенный уровень в Form B) —
            # рендерим маркер с пустым телом, чтобы сохранить позицию в нумерации.
            if not has_para:
                self._paragraphs.append(
                    self._make_item_paragraph(
                        [],
                        marker_style=marker_style,
                        counter=counter,
                        full_path=full_path,
                        level=clamped_level,
                        delimiter=delimiter,
                    )
                )
            first_para_emitted = False
            for kind, payload in blocks:
                if kind == "para":
                    assert isinstance(payload, list)
                    if not first_para_emitted:
                        first_para_emitted = True
                        self._paragraphs.append(
                            self._make_item_paragraph(
                                payload,
                                marker_style=marker_style,
                                counter=counter,
                                full_path=full_path,
                                level=clamped_level,
                                delimiter=delimiter,
                            )
                        )
                    else:
                        self._paragraphs.append(
                            self._make_continuation_paragraph(
                                payload, level=clamped_level
                            )
                        )
                else:  # "list"
                    assert isinstance(payload, ast.List)
                    sub_start = payload.start if payload.ordered else 1
                    self._build(
                        payload,
                        level=level + 1,
                        start=sub_start,
                        parent_path=full_path,
                    )
            counter += 1

    def _make_item_paragraph(
        self,
        children: list[ast.InlineNode],
        *,
        marker_style: str,
        counter: int,
        full_path: list[int] | None,
        level: int,
        delimiter: str | None = None,
    ) -> Paragraph:
        marker = self._format_marker(
            marker_style=marker_style,
            counter=counter,
            full_path=full_path,
            delimiter=delimiter,
        )
        paragraph = Paragraph(
            self._parent, self._config, bibliography=self._bibliography
        )
        # Иерархические маркеры (L≥2) шире `indent_per_level` — таб глотается
        # LibreOffice. Заменяем `\t` на 2 пробела, чтобы гарантированно был
        # видимый зазор между маркером и текстом. Не-иерархические маркеры —
        # таб (он держит выравнивание текста в колонку).
        is_hierarchical = full_path is not None and len(full_path) > 1
        separator = "  " if is_hierarchical else "\t"
        paragraph.docx_paragraph.add_run(f"{marker}{separator}")
        paragraph.add_inline_nodes(children)
        self._apply_layout(paragraph, level=level)
        _disable_style_numbering(paragraph)
        return paragraph

    def _format_marker(
        self,
        *,
        marker_style: str,
        counter: int,
        full_path: list[int] | None,
        delimiter: str | None = None,
    ) -> str:
        if marker_style == "bullet":
            return self._spec.bullet_marker
        if marker_style in _ALPHABETS_BY_STYLE:
            alphabet = _ALPHABETS_BY_STYLE[marker_style]
            return _format_alpha(self._spec.alphabetic_format, counter, alphabet)
        # arabic / любой неизвестный → арабские цифры.
        # Иерархическая цепочка → собранный путь, иначе локальный counter.
        if full_path:
            n_value: str | int = _HIERARCHICAL_SEPARATOR.join(str(c) for c in full_path)
        else:
            n_value = counter
        # Литеральный delimiter из md (``"."`` или ``")"``) перетирает конфиг.
        # Конфиг ``numbered_format`` остаётся для редких форматов (``№{n}``,
        # ``({n})``) — он применяется когда delimiter не задан или дефолтный.
        if delimiter is not None:
            return f"{n_value}{delimiter}"
        fmt = self._spec.numbered_format
        try:
            return fmt.format(n=n_value)
        except (KeyError, IndexError):
            return fmt

    def _make_continuation_paragraph(
        self, children: list[ast.InlineNode], *, level: int
    ) -> Paragraph:
        """Параграф-продолжение item-а: без маркера, выровнен по тексту item-а."""

        paragraph = Paragraph(
            self._parent, self._config, bibliography=self._bibliography
        )
        paragraph.add_inline_nodes(children)
        pf = paragraph.docx_paragraph.paragraph_format
        left_indent = Length(
            int(self._indent_left) + int(self._indent_per_level) * (level - 1)
        )
        pf.left_indent = left_indent
        pf.first_line_indent = Length(0)
        pf.space_before = 0
        pf.space_after = 0
        _disable_style_numbering(paragraph)
        return paragraph

    def _apply_layout(self, paragraph: Paragraph, *, level: int) -> None:
        pf = paragraph.docx_paragraph.paragraph_format
        left_indent = Length(
            int(self._indent_left) + int(self._indent_per_level) * (level - 1)
        )
        pf.left_indent = left_indent
        # Висячий отступ — маркер выезжает влево от текста ровно на indent_per_level.
        pf.first_line_indent = Length(-int(self._indent_per_level))
        # Tab-стоп ровно на ширине отступа, чтобы текст после ``\t`` встал в колонку.
        pf.tab_stops.add_tab_stop(left_indent)
        # Внутри списка не нужен интервал между пунктами — рендер задаёт его сам.
        pf.space_before = 0
        pf.space_after = 0

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        for paragraph in self._paragraphs:
            for info in paragraph.render(previous_rendered, copy(layout_state)):
                if isinstance(info, RenderedInfo):
                    layout_state.add_height(info.height)
                    previous_rendered = info
                yield info


def _resolve_marker_style(node: ast.List) -> str:
    """Привести ``ast.List.marker_style`` к финальному виду, учитывая ``ordered``."""

    if not node.ordered:
        return "bullet"
    if node.marker_style in _ALPHABETS_BY_STYLE:
        return node.marker_style
    return "arabic"


def _format_alpha(fmt: str, counter: int, alphabet: str) -> str:
    """Подставить букву в формат ``"{a})"``. ``counter`` — 1-based индекс буквы."""

    idx = max(0, counter - 1)
    # Защита от выхода за алфавит — отдаём арабский номер вместо буквы.
    letter = str(counter) if idx >= len(alphabet) else alphabet[idx]
    try:
        return fmt.format(a=letter, n=counter)
    except (KeyError, IndexError):
        return fmt


def _item_blocks(
    item: ast.ListItem,
) -> list[tuple[str, list[ast.InlineNode] | ast.List]]:
    """Разложить детей item-а в упорядоченную последовательность блоков.

    Каждый элемент — пара ``("para", inlines)`` или ``("list", sub_list)``.
    Порядок сохраняется: continuation-параграфы и вложенные списки могут
    чередоваться, рендер должен пройти их в исходном порядке.
    """

    blocks: list[tuple[str, list[ast.InlineNode] | ast.List]] = []
    for child in item.children:
        if isinstance(child, ast.Paragraph):
            blocks.append(("para", list(child.children)))
        elif isinstance(child, ast.List):
            blocks.append(("list", child))
        elif isinstance(child, ast.Text):
            blocks.append(("para", [child]))
    return blocks


def _disable_style_numbering(paragraph: Paragraph) -> None:
    """Заглушаем стилевую автонумерацию через явный ``<w:numId w:val="0"/>``.

    Без этого Word/LibreOffice могут навесить на параграф нумерацию из
    ``numbering.xml``, которая встанет рядом с нашим inline-маркером и даст
    дублирование вида ``1) 1.``.
    """

    ppr = paragraph.docx_paragraph._p.get_or_add_pPr()
    ppr.append(
        create_element(
            "w:numPr",
            [
                create_element("w:ilvl", {"w:val": "0"}),
                create_element("w:numId", {"w:val": "0"}),
            ],
        )
    )
