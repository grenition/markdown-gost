"""Списки: ordered/unordered, вложенные до 4 уровней.

Bullet и arabic списки (``lists.mode: native``, дефолт) рендерятся нативной
нумерацией Word: параграф несёт ``w:numPr``, форматы маркеров и геометрия
(висячий отступ) живут в ``numbering.xml``. На каждый корень цепочки выдаётся
свежий ``w:num`` — нумерация не продолжается между соседними списками;
вложенные уровни цепочки делят один num (``ilvl`` = относительная глубина).
Bullet-цепочка: «—» на L1, глубже — ``1)`` (``bullet_nested_format``).
Arabic-цепочка: иерархические маркеры ``1.``, ``1.1.`` через составной
``lvlText`` (``%1.%2.``).

Буквенные списки (``а)``) остаются на вычисляемых литеральных маркерах:
ГОСТ 7.32-2017 запрещает буквы ``ё, з, й, о, ч, ъ, ы, ь``, а нумерация Word
такой фильтр не выражает. Режим ``lists.mode: inline`` возвращает литеральные
маркеры для всех списков.
"""

from __future__ import annotations

from collections.abc import Generator
from copy import copy
from dataclasses import dataclass
from typing import Any

from docx.shared import Length

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable
from markdown_gost.renderable.numbering import (
    LevelSpec,
    Numbering,
    apply_num_pr,
    get_numbering,
)
from markdown_gost.renderable.paragraph import Paragraph

from ._oxml import create_element

_MAX_LEVEL = 4

# Сколько уровней описываем в abstractNum (Word поддерживает 9; глубина
# вложенности md-списков практически не превышает 4-5).
_NUMBERING_LEVELS = 9

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


@dataclass(frozen=True)
class _ChainCtx:
    """Нативная цепочка одного вида: общий numId + относительная глубина."""

    kind: str  # "bullet" | "arabic"
    num_id: int
    rel_level: int  # 0-based ilvl этого узла цепочки


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
        self._native = self._spec.mode == "native"
        self._numbering: Numbering | None = None

        self._paragraphs: list[Paragraph] = []
        self._build(
            node,
            level=1,
            start=node.start if node.ordered else 1,
            parent_path=[],
            parent_ctx=None,
        )

    def _build(
        self,
        node: ast.List,
        *,
        level: int,
        start: int,
        parent_path: list[int] | None,
        parent_ctx: _ChainCtx | None,
    ) -> None:
        clamped_level = min(level, _MAX_LEVEL)
        counter = start
        marker_style = _resolve_marker_style(node)
        delimiter = node.delimiter if marker_style == "arabic" else None
        ctx = self._chain_ctx(node, marker_style=marker_style, level=level, parent_ctx=parent_ctx)
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
                        ctx=ctx,
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
                                ctx=ctx,
                            )
                        )
                    else:
                        self._paragraphs.append(
                            self._make_continuation_paragraph(payload, level=clamped_level)
                        )
                else:  # "list"
                    assert isinstance(payload, ast.List)
                    sub_start = payload.start if payload.ordered else 1
                    self._build(
                        payload,
                        level=level + 1,
                        start=sub_start,
                        parent_path=full_path,
                        parent_ctx=ctx,
                    )
            counter += 1

    def _chain_ctx(
        self,
        node: ast.List,
        *,
        marker_style: str,
        level: int,
        parent_ctx: _ChainCtx | None,
    ) -> _ChainCtx | None:
        """Нативный контекст узла: None → литеральные маркеры (alpha/inline)."""
        if not self._native or marker_style in _ALPHABETS_BY_STYLE:
            return None
        kind = "bullet" if marker_style == "bullet" else "arabic"
        if parent_ctx is not None and parent_ctx.kind == kind:
            # Продолжение цепочки: тот же num, глубже на уровень.
            ctx = _ChainCtx(kind=kind, num_id=parent_ctx.num_id, rel_level=parent_ctx.rel_level + 1)
            if kind == "arabic" and node.start != 1:
                self._get_numbering().override_start(ctx.num_id, ctx.rel_level, node.start)
            return ctx
        num_id = self._allocate_num(
            marker_style=marker_style,
            delimiter=node.delimiter if kind == "arabic" else None,
            level=level,
            start=node.start if node.ordered else 1,
        )
        return _ChainCtx(kind=kind, num_id=num_id, rel_level=0)

    def _allocate_num(
        self,
        *,
        marker_style: str,
        delimiter: str | None,
        level: int,
        start: int,
    ) -> int:
        per_level = int(self._indent_per_level)
        levels = [
            LevelSpec(
                num_fmt=num_fmt,
                lvl_text=lvl_text,
                # Геометрия уровня: как у прямых отступов — left растёт с
                # абсолютной глубиной, зажимается на _MAX_LEVEL.
                left=int(self._indent_left) + per_level * min(level - 1 + rel, _MAX_LEVEL - 1),
                hanging=per_level,
            )
            for rel, (num_fmt, lvl_text) in enumerate(
                self._level_formats(marker_style=marker_style, delimiter=delimiter)
            )
        ]
        return self._get_numbering().new_num(levels, start=start)

    def _level_formats(self, *, marker_style: str, delimiter: str | None) -> list[tuple[str, str]]:
        """``(numFmt, lvlText)`` для rel-уровней 0..N цепочки."""
        if marker_style == "bullet":
            return [("bullet", self._spec.bullet_marker)] + [
                ("decimal", _placeholder_text(self._spec.bullet_nested_format, rel))
                for rel in range(1, _NUMBERING_LEVELS)
            ]
        # arabic: литеральный delimiter из md перетирает конфиг
        # ``numbered_format`` (который остаётся для редких форматов ``№{n}``).
        if delimiter is not None:
            prefix, suffix = "", delimiter
        else:
            fmt = self._spec.numbered_format
            prefix, sep, suffix = fmt.partition("{n}")
            if not sep:
                # Дегенеративный формат без плейсхолдера — литеральный текст.
                return [("decimal", fmt)] * _NUMBERING_LEVELS
        return [
            (
                "decimal",
                prefix + _HIERARCHICAL_SEPARATOR.join(f"%{i}" for i in range(1, rel + 2)) + suffix,
            )
            for rel in range(_NUMBERING_LEVELS)
        ]

    def _get_numbering(self) -> Numbering:
        if self._numbering is None:
            self._numbering = get_numbering(self._parent)
        return self._numbering

    def _make_item_paragraph(
        self,
        children: list[ast.InlineNode],
        *,
        marker_style: str,
        counter: int,
        full_path: list[int] | None,
        level: int,
        delimiter: str | None = None,
        ctx: _ChainCtx | None = None,
    ) -> Paragraph:
        if ctx is not None:
            return self._make_native_item_paragraph(children, ctx=ctx)
        return self._make_inline_item_paragraph(
            children,
            marker_style=marker_style,
            counter=counter,
            full_path=full_path,
            level=level,
            delimiter=delimiter,
        )

    def _make_native_item_paragraph(
        self, children: list[ast.InlineNode], *, ctx: _ChainCtx
    ) -> Paragraph:
        """Пункт нативного списка: без маркера в тексте, геометрия — в numbering."""
        paragraph = Paragraph(self._parent, self._config, bibliography=self._bibliography)
        paragraph.add_inline_nodes(children)
        pf = paragraph.docx_paragraph.paragraph_format
        # Внутри списка не нужен интервал между пунктами — рендер задаёт его сам.
        pf.space_before = 0
        pf.space_after = 0
        apply_num_pr(paragraph.docx_paragraph, ilvl=ctx.rel_level, num_id=ctx.num_id)
        return paragraph

    def _make_inline_item_paragraph(
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
        paragraph = Paragraph(self._parent, self._config, bibliography=self._bibliography)
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

        paragraph = Paragraph(self._parent, self._config, bibliography=self._bibliography)
        paragraph.add_inline_nodes(children)
        pf = paragraph.docx_paragraph.paragraph_format
        left_indent = Length(int(self._indent_left) + int(self._indent_per_level) * (level - 1))
        pf.left_indent = left_indent
        pf.first_line_indent = Length(0)
        pf.space_before = 0
        pf.space_after = 0
        if not self._native:
            # В native-режиме продолжение не касается нумерации вовсе; в
            # inline-режиме глушим стилевую автонумерацию как у item-ов.
            _disable_style_numbering(paragraph)
        return paragraph

    def _apply_layout(self, paragraph: Paragraph, *, level: int) -> None:
        """Прямая геометрия — только для литеральных (alpha/inline) списков."""
        pf = paragraph.docx_paragraph.paragraph_format
        left_indent = Length(int(self._indent_left) + int(self._indent_per_level) * (level - 1))
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


def _placeholder_text(fmt: str, rel_level: int) -> str:
    """``{n})`` → ``%2)`` для rel-уровня (плейсхолдер своего счётчика)."""
    if "{n}" not in fmt:
        return fmt
    return fmt.replace("{n}", f"%{rel_level + 1}")


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

    Только для литеральных маркеров (alpha-списки, режим inline): без этого
    Word/LibreOffice могут навесить на параграф нумерацию из
    ``numbering.xml``, которая встанет рядом с нашим маркером и даст
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
