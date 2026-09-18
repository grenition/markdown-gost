from __future__ import annotations

import pytest
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.appendix import Appendix
from markdown_gost.renderable.base import RenderedInfo


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


def test_appendix_renders_centered_uppercase_heading_with_page_break(config) -> None:
    document = build_document(config)
    renderable = Appendix(
        document,
        config,
        ast.AppendixStart(title="Исходные данные"),
        Numberer(),
    )

    items = [
        item
        for item in renderable.render(
            None,
            LayoutState(
                max_height=document.sections[0].page_height,
                max_width=document.sections[0].page_width,
            ),
        )
        if isinstance(item, RenderedInfo)
    ]

    assert len(items) == 2
    label, title = [item.docx_element for item in items]
    assert label.text == "ПРИЛОЖЕНИЕ А"
    assert label.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER
    assert label.paragraph_format.page_break_before is True
    assert title.text == "ИСХОДНЫЕ ДАННЫЕ"
    assert title.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER

    assert renderable.letter == "А"
