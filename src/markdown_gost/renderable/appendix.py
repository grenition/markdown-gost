from __future__ import annotations

from collections.abc import Generator
from typing import Any

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Length
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.paragraph_sizer import ParagraphSizer
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable


class Appendix(Renderable):
    def __init__(
        self,
        parent: Any,
        config: Config,
        node: ast.AppendixStart,
        numberer: Numberer,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._letter = numberer.start_appendix()

        self._label_paragraph = self._make_paragraph(f"ПРИЛОЖЕНИЕ {self._letter}")
        self._label_paragraph.paragraph_format.page_break_before = True
        self._title_paragraph: DocxParagraph | None = None
        if node.title:
            self._title_paragraph = self._make_paragraph(node.title.upper())

    @property
    def letter(self) -> str:
        return self._letter

    @property
    def title(self) -> str | None:
        return self._node.title

    @property
    def index_text(self) -> str:
        if self._node.title:
            return f"ПРИЛОЖЕНИЕ {self._letter} {self._node.title}"
        return f"ПРИЛОЖЕНИЕ {self._letter}"

    def _make_paragraph(self, text: str) -> DocxParagraph:
        paragraph = DocxParagraph(create_element("w:p"), self._parent)
        paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        pf = paragraph.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = 0
        pf.space_after = 0
        run = paragraph.add_run(text)
        run.font.name = self._config.font.family
        return paragraph

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        info = self._render_paragraph(self._label_paragraph, previous_rendered, layout_state)
        yield info
        layout_state.add_height(info.height)

        if self._title_paragraph is None:
            return
        title_info = self._render_paragraph(self._title_paragraph, info, layout_state)
        yield title_info
        layout_state.add_height(title_info.height)

    def _render_paragraph(
        self,
        paragraph: DocxParagraph,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> RenderedInfo:
        previous_paragraph: DocxParagraph | None = None
        if previous_rendered is not None and isinstance(
            previous_rendered.docx_element, DocxParagraph
        ):
            previous_paragraph = previous_rendered.docx_element
        height = (
            ParagraphSizer(
                paragraph,
                previous_paragraph,
                layout_state.max_width,
            )
            .calculate_height()
            .full
        )
        if paragraph.paragraph_format.page_break_before and layout_state.current_page_height > 0:
            height = Length(int(height) + int(layout_state.remaining_page_height))
        return RenderedInfo(paragraph, Length(int(height)))


class AppendixEnd(Renderable):
    """Non-visual marker restoring the main-document numbering context."""

    def render(
        self, previous_rendered: RenderedInfo | None, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        yield from ()
