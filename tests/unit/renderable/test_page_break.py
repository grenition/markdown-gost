"""Юнит-тесты для :class:`markdown_gost.renderable.page_break.PageBreak`."""

from __future__ import annotations

import pytest
from docx.oxml.ns import qn
from docx.shared import Pt

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutTracker
from markdown_gost.renderable.page_break import PageBreak


@pytest.fixture
def document():
    return build_document(load_config_from_string("preset: gost-7-32-2017\n"))


def test_page_break_creates_w_br_page(document):
    pb = PageBreak(document)
    runs = pb.docx_paragraph._p.findall(qn("w:r"))
    assert len(runs) == 1
    br = runs[0].find(qn("w:br"))
    assert br is not None
    assert br.get(qn("w:type")) == "page"


def test_page_break_run_size_is_one_pt(document):
    pb = PageBreak(document)
    assert pb.docx_paragraph.runs[0].font.size == Pt(1)


def test_page_break_zero_spacing(document):
    pb = PageBreak(document)
    pf = pb.docx_paragraph.paragraph_format
    assert pf.space_before == 0
    assert pf.space_after == 0


def test_page_break_render_advances_to_next_page(document):
    pb = PageBreak(document)
    section = document.sections[0]
    tracker = LayoutTracker(
        max_height=section.page_height - section.top_margin - section.bottom_margin,
        max_width=section.page_width - section.left_margin - section.right_margin,
    )
    info = next(pb.render(None, tracker.current_state))
    tracker.add_height(info.height)
    assert tracker.is_new_page
    assert tracker.current_state.page == 2
