"""Принудительный разрыв страницы (``ast.PageBreak``)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from docx.shared import Length, Pt
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.paragraph_sizer import ParagraphSizer
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable

from ._oxml import create_element


class PageBreak(Renderable):
    def __init__(self, parent: Any) -> None:
        self._docx_paragraph = DocxParagraph(
            create_element(
                "w:p",
                [create_element("w:r", [create_element("w:br", {"w:type": "page"})])],
            ),
            parent,
        )
        self._docx_paragraph.runs[0].font.size = Pt(1)
        self._docx_paragraph.paragraph_format.space_before = 0
        self._docx_paragraph.paragraph_format.space_after = 0

    @property
    def docx_paragraph(self) -> DocxParagraph:
        return self._docx_paragraph

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        # Высота — до конца страницы; гарантирует что layout_tracker.page вырастет.
        line_height = (
            ParagraphSizer(self._docx_paragraph, None, layout_state.max_width)
            .calculate_height()
            .line_height
        )
        height = max(layout_state.remaining_page_height, line_height)
        yield RenderedInfo(self._docx_paragraph, Length(int(height)))
