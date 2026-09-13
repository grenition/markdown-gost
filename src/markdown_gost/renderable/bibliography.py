from __future__ import annotations

from collections.abc import Generator
from copy import copy
from typing import Any

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable
from markdown_gost.renderable.paragraph import Paragraph


class Bibliography(Renderable):
    def __init__(
        self,
        parent: Any,
        config: Config,
        node: ast.Bibliography,
        index: BibliographyIndex,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._index = index
        self._paragraphs = self._build_paragraphs()

    def _build_paragraphs(self) -> list[Paragraph]:
        paragraphs: list[Paragraph] = []
        for entry in self._index.entries():
            paragraph = Paragraph(self._parent, self._config, bibliography=self._index)
            paragraph.docx_paragraph.add_run(f"{self._format_number(entry.number)} ")
            paragraph.docx_paragraph.add_run(self._index.format_entry(entry.source.id))
            paragraph.docx_paragraph.paragraph_format.first_line_indent = parse_length(
                self._config.paragraph.indent_first_line
            )
            paragraphs.append(paragraph)
        return paragraphs

    def _format_number(self, number: int) -> str:
        try:
            return self._config.bibliography.entry_number_format.format(n=number)
        except (KeyError, IndexError):
            return self._config.bibliography.entry_number_format

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        for paragraph in self._paragraphs:
            for item in paragraph.render(previous_rendered, copy(layout_state)):
                if isinstance(item, RenderedInfo):
                    layout_state.add_height(item.height)
                    previous_rendered = item
                yield item
