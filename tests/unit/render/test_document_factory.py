"""Юнит-тесты build_document: применение конфига к docx-документу."""

from __future__ import annotations

import pytest
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.render.document_factory import build_document


@pytest.fixture
def config():
    return load_config_from_string("preset: default\n")


def test_returns_docx_document(config):
    document = build_document(config)
    assert document.sections, "ожидаем хотя бы одну секцию"


_TWIP_TOLERANCE = 1000  # ~1.5 twip — python-docx делает round-trip EMU↔twips.


def test_page_size_a4_portrait(config):
    document = build_document(config)
    section = document.sections[0]
    assert abs(section.page_width - Cm(21)) <= _TWIP_TOLERANCE
    assert abs(section.page_height - Cm(29.7)) <= _TWIP_TOLERANCE


def test_page_margins_match_default_preset(config):
    document = build_document(config)
    section = document.sections[0]
    assert abs(section.top_margin - Cm(2)) <= _TWIP_TOLERANCE
    assert abs(section.bottom_margin - Cm(1.25)) <= _TWIP_TOLERANCE
    assert abs(section.left_margin - Cm(2.5)) <= _TWIP_TOLERANCE
    assert abs(section.right_margin - Cm(1)) <= _TWIP_TOLERANCE


def test_normal_style_font_and_size(config):
    document = build_document(config)
    style = document.styles["Normal"]
    assert style.font.name == "Times New Roman"
    assert style.font.size == Pt(14)


def test_normal_style_alignment_and_indent(config):
    document = build_document(config)
    style = document.styles["Normal"]
    assert style.paragraph_format.alignment == WD_PARAGRAPH_ALIGNMENT.JUSTIFY
    assert abs(style.paragraph_format.first_line_indent - Cm(1.25)) <= _TWIP_TOLERANCE


def test_heading_1_is_bold(config):
    document = build_document(config)
    style = document.styles["Heading 1"]
    assert style.font.bold is True


def test_heading_1_uppercase_caps_marker(config):
    document = build_document(config)
    style = document.styles["Heading 1"]
    rpr = style.element.find(qn("w:rPr"))
    assert rpr is not None
    caps = rpr.find(qn("w:caps"))
    assert caps is not None, "ожидался <w:caps> для Heading 1 при uppercase=true"


def test_heading_uppercase_false_removes_existing_caps_marker():
    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  headings:\n"
        "    levels:\n"
        "      1:\n"
        "        uppercase: false\n"
    )

    document = build_document(cfg)
    style = document.styles["Heading 1"]
    rpr = style.element.find(qn("w:rPr"))

    assert rpr is not None
    assert rpr.find(qn("w:caps")) is None


def test_structural_heading_style_uses_dedicated_formatting(config):
    document = build_document(config)
    style = document.styles["MD2GOST Structural Heading"]

    assert style.paragraph_format.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER
    assert style.paragraph_format.first_line_indent == 0
    assert style.paragraph_format.page_break_before is True
    rpr = style.element.find(qn("w:rPr"))
    assert rpr is not None
    assert rpr.find(qn("w:caps")) is not None
    ppr = style.element.find(qn("w:pPr"))
    assert ppr is None or ppr.find(qn("w:numPr")) is None


def test_body_is_empty(config):
    """Шаблонный body должен быть очищен."""
    document = build_document(config)
    paragraphs = document.paragraphs
    # Допустим один пустой sectPr-параграф или 0 параграфов; главное — нет лишнего текста.
    text = "\n".join(p.text for p in paragraphs).strip()
    assert text == ""
