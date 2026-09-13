"""Заголовки h1..h6 с многоуровневой нумерацией ``1.2.3.``."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from docx.oxml.ns import qn
from docx.shared import Length
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import STRUCTURAL_HEADING_STYLE
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.paragraph_sizer import ParagraphSizer
from markdown_gost.renderable.base import RenderedInfo, SubRenderable
from markdown_gost.renderable.paragraph import Paragraph

from ._oxml import create_element

_MAX_LEVEL = 6


class Heading(Paragraph):
    """Заголовок уровня 1..6.

    Если ``numbered=False`` (атрибут ``.unnumbered``), H1 с известным названием
    структурного элемента рендерится отдельным стилем и не занимает слот
    нумерации. Остальные ненумерованные заголовки сохраняют legacy-поведение:
    префикс не добавляется, ``w:numPr`` снимается, но счётчик уровня
    инкрементируется.
    """

    def __init__(
        self,
        parent: Any,
        config: Config,
        node: ast.Heading,
        numberer: Numberer,
    ) -> None:
        if not 1 <= node.level <= _MAX_LEVEL:
            raise ValueError(f"heading level must be in 1..{_MAX_LEVEL}, got {node.level}")
        raw_text = _collect_text(node.children)
        self._is_structural = _is_structural_heading(config, node, raw_text)
        style = STRUCTURAL_HEADING_STYLE if self._is_structural else f"Heading {node.level}"
        super().__init__(parent, config, style=style)
        self._level = node.level
        self._numbered = node.numbered
        self._in_appendix = numberer.current_appendix is not None
        self._rendered_page = 0
        # Чистый текст заголовка (без числового префикса) — нужен для
        # ``RenderIndex`` (TOC) и для anchor'а закладки.
        self._raw_text = raw_text
        # Префикс ``"1.2.3"`` — выставляется в ``_inject_numbering``, ``None``
        # для ненумерованных заголовков и для ``headings.numbering=none``.
        self._number_prefix: str | None = None

        self._inject_numbering(numberer, node)
        self.add_inline_nodes(node.children)

    @property
    def level(self) -> int:
        return self._level

    @property
    def is_numbered(self) -> bool:
        return self._numbered

    @property
    def rendered_page(self) -> int:
        return self._rendered_page

    @property
    def text(self) -> str:
        return self._docx_paragraph.text

    @property
    def raw_text(self) -> str:
        """Текст заголовка без числового префикса — для TOC/anchor."""

        return self._raw_text

    @property
    def number(self) -> str | None:
        """Префикс нумерации ``"1.2.3"`` или ``None`` для ненумерованного."""

        return self._number_prefix

    # ---- private -----------------------------------------------------------

    def _inject_numbering(self, numberer: Numberer, node: ast.Heading) -> None:
        if self._is_structural:
            return
        if self._config.headings.numbering == "none":
            self._strip_numbering()
            return
        # Инкрементируем счётчик уровня даже для ненумерованных заголовков —
        # они занимают полноценный слот в иерархии, чтобы вложенные подзаголовки
        # получали корректный родительский префикс.
        prefix = numberer.bump_heading(self._level)
        if not self._numbered:
            self._strip_numbering()
            return
        self._number_prefix = prefix
        separator = " " if self._config.headings.leading_space_in_numbered else " "
        leading_text = f"{prefix}{separator}"
        # Стили Heading 1..6 в base.docx несут собственный <w:numPr>. Заглушаем
        # его явным numId=0 на уровне параграфа — иначе manual prefix задвоится
        # стилевой автонумерацией ('1     1 ВВЕДЕНИЕ').
        self._strip_numbering()
        leading_run = self._docx_paragraph.add_run(leading_text)
        style = self._docx_paragraph.style
        if style is not None:
            leading_run.bold = style.font.bold

    def _strip_numbering(self) -> None:
        ppr = self._docx_paragraph._p.get_or_add_pPr()
        ppr.append(
            create_element(
                "w:numPr",
                [
                    create_element("w:ilvl", {"w:val": "0"}),
                    create_element("w:numId", {"w:val": "0"}),
                ],
            )
        )

    # ---- render ------------------------------------------------------------

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        remaining_height = layout_state.remaining_page_height

        # h1 всегда с новой страницы (кроме первой страницы документа и случая,
        # когда непосредственно перед ним стоит пустой служебный параграф или
        # параграф с уже встроенным разрывом страницы — например, трейлер
        # titlepage-шаблона).
        prev_para: DocxParagraph | None = None
        if previous_rendered is not None and isinstance(
            previous_rendered.docx_element, DocxParagraph
        ):
            prev_para = previous_rendered.docx_element
        prev_has_page_break = prev_para is not None and any(
            br.get(qn("w:type")) == "page" for br in prev_para._p.iter(qn("w:br"))
        )
        if (
            self._page_break_before_enabled()
            and layout_state.current_page_height > 0
            and not (
                prev_para is not None
                and (prev_para.text == "\n" or prev_has_page_break)
            )
        ):
            self.page_break_before = True
        else:
            self.page_break_before = False

        previous_docx_paragraph: DocxParagraph | None = None
        if previous_rendered is not None and isinstance(
            previous_rendered.docx_element, DocxParagraph
        ):
            previous_docx_paragraph = previous_rendered.docx_element

        height_data = ParagraphSizer(
            self._docx_paragraph,
            previous_docx_paragraph,
            layout_state.max_width,
        ).calculate_height()

        if layout_state.current_page_height == 0 and layout_state.page != 1:
            height_data.before = Length(0)

        # Если заголовок плюс 3 строки текста не влезают — двигаем на новую страницу.
        if (
            (height_data.lines + 3 - 1) * height_data.line_spacing + 1
        ) * height_data.line_height > layout_state.remaining_page_height:
            self._docx_paragraph.paragraph_format.space_before = 0
            height = height_data.full - height_data.before
            self.page_break_before = True
        else:
            height = height_data.full

        if self.page_break_before:
            height += remaining_height

        layout_state.add_height(Length(int(height)))
        self._rendered_page = layout_state.page

        yield RenderedInfo(self._docx_paragraph, Length(int(height)))

    def _page_break_before_enabled(self) -> bool:
        if self._in_appendix:
            return False
        if self._is_structural:
            return self._config.headings.structural.page_break_before
        spec = self._config.headings.levels.get(self._level)
        return bool(spec.page_break_before) if spec is not None else False


def _collect_text(children: list[ast.InlineNode]) -> str:
    """Собрать «чистый» текст заголовка из inline-AST.

    Учитываем ``Text`` и рекурсивно — контейнеры с ``children``
    (``Strong``/``Emphasis``/``Underline``/``Strikethrough``/``Link``).
    Inline-формулы и картинки опускаем — на TOC и anchor они влиять не должны.
    """

    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ast.Text):
            parts.append(node.text)
            return
        if isinstance(node, ast.InlineCode):
            parts.append(node.code)
            return
        if isinstance(node, ast.LineBreak):
            parts.append(" ")
            return
        if hasattr(node, "children"):
            for child in node.children:
                walk(child)

    for child in children:
        walk(child)
    return "".join(parts).strip()


def _is_structural_heading(config: Config, node: ast.Heading, raw_text: str) -> bool:
    if node.numbered or node.level != 1:
        return False
    normalized = _normalize_structural_title(raw_text)
    titles = [_normalize_structural_title(title) for title in config.headings.structural_titles]
    if normalized in titles:
        return True
    return normalized.startswith("СПИСОК ") and any(
        title.startswith("СПИСОК ") for title in titles
    )


def _normalize_structural_title(text: str) -> str:
    return " ".join(text.upper().strip().rstrip(".").split())
