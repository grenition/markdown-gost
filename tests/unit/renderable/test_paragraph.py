"""Юнит-тесты для :class:`markdown_gost.renderable.paragraph.Paragraph`."""

from __future__ import annotations

import pytest
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.renderable.paragraph import Paragraph


@pytest.fixture
def config():
    return load_config_from_string("preset: default\n")


@pytest.fixture
def document(config):
    return build_document(config)


def test_simple_text_paragraph_uses_normal_style(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Text(text="Привет, мир")])
    assert p.docx_paragraph.style.name == "Normal"
    assert p.docx_paragraph.text == "Привет, мир"


def test_strong_run_is_bold(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Strong(children=[ast.Text(text="жирный")])])
    runs = p.docx_paragraph.runs
    assert len(runs) >= 1
    assert any(r.bold for r in runs)
    assert "жирный" in p.docx_paragraph.text


def test_emphasis_run_is_italic(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Emphasis(children=[ast.Text(text="курсив")])])
    runs = p.docx_paragraph.runs
    assert any(r.italic for r in runs)
    assert "курсив" in p.docx_paragraph.text


def test_inline_code_uses_configured_font_and_size(document, config):
    # Дефолт: Consolas, 14pt, italic=False, quotes=False.
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.InlineCode(code="x = 1")])
    runs = [r for r in p.docx_paragraph.runs if r.text]
    assert runs, "ожидался хотя бы один run с текстом кода"
    code_run = next(r for r in runs if "x" in r.text or "1" in r.text)
    assert code_run.font.name == "Consolas"
    assert code_run.font.size == Pt(14)
    assert not code_run.italic
    assert "x = 1" in p.docx_paragraph.text


def test_inline_code_quotes_wrap_when_enabled():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  paragraph:\n    inline_code:\n      quotes: true\n"
    )
    doc = build_document(cfg)
    p = Paragraph(doc, cfg)
    p.add_inline_nodes([ast.InlineCode(code="x = 1")])
    assert "«x = 1»" in p.docx_paragraph.text


def test_inline_code_italic_override():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  paragraph:\n    inline_code:\n      italic: true\n"
    )
    doc = build_document(cfg)
    p = Paragraph(doc, cfg)
    p.add_inline_nodes([ast.InlineCode(code="x")])
    runs = [r for r in p.docx_paragraph.runs if r.text]
    assert any(r.italic for r in runs)


def test_inline_code_font_and_size_override():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  paragraph:\n    inline_code:\n"
        "      font: Courier New\n      size: 12pt\n"
    )
    doc = build_document(cfg)
    p = Paragraph(doc, cfg)
    p.add_inline_nodes([ast.InlineCode(code="abc")])
    code_run = next(r for r in p.docx_paragraph.runs if r.text == "abc")
    assert code_run.font.name == "Courier New"
    assert code_run.font.size == Pt(12)


def test_line_break_collapses_to_space(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes(
        [ast.Text(text="до"), ast.LineBreak(soft=True), ast.Text(text="после")]
    )
    assert p.docx_paragraph.text == "до после"


def test_strikethrough_run_is_struck(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Strikethrough(children=[ast.Text(text="зачёркнуто")])])
    runs = [r for r in p.docx_paragraph.runs if r.text]
    assert any(r.font.strike for r in runs)
    assert "зачёркнуто" in p.docx_paragraph.text


def test_underline_run_is_underlined(document, config):
    from docx.enum.text import WD_UNDERLINE

    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Underline(children=[ast.Text(text="подчёркнуто")])])
    runs = [r for r in p.docx_paragraph.runs if r.text]
    assert any(r.font.underline == WD_UNDERLINE.SINGLE for r in runs)
    assert "подчёркнуто" in p.docx_paragraph.text


def test_underline_combined_with_bold(document, config):
    from docx.enum.text import WD_UNDERLINE

    p = Paragraph(document, config)
    p.add_inline_nodes(
        [
            ast.Strong(
                children=[ast.Underline(children=[ast.Text(text="жирно-подчёркнуто")])]
            )
        ]
    )
    runs = [r for r in p.docx_paragraph.runs if r.text]
    assert any(
        r.bold and r.font.underline == WD_UNDERLINE.SINGLE for r in runs
    ), f"runs={[(r.text, r.bold, r.font.underline) for r in runs]}"


def test_mixed_runs_preserve_text_order(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes(
        [
            ast.Text(text="простой "),
            ast.Strong(children=[ast.Text(text="жирный")]),
            ast.Text(text=" хвост"),
        ]
    )
    assert p.docx_paragraph.text.startswith("простой ")
    assert "жирный" in p.docx_paragraph.text
    assert p.docx_paragraph.text.endswith("хвост")


def test_alignment_from_config_applied_to_normal_style(document, config):
    # Конфиг говорит justify; стиль Normal должен иметь justify alignment.
    style = document.styles["Normal"]
    assert style.paragraph_format.alignment == WD_PARAGRAPH_ALIGNMENT.JUSTIFY


def test_first_line_indent_from_config_applied_to_normal_style(document, config):
    from docx.shared import Cm

    style = document.styles["Normal"]
    indent = style.paragraph_format.first_line_indent
    assert indent is not None
    # python-docx сохраняет в twips → допуск ~1500 EMU после round-trip.
    assert abs(indent - Cm(1.25)) <= 1000


def test_hyphen_replaced_with_no_break_hyphen(document, config):
    from docx.oxml.ns import qn

    p = Paragraph(document, config)
    p.add_inline_nodes([ast.Text(text="кое-что")])
    nodes = p.docx_paragraph._p.findall(qn("w:r"))
    has_no_break = any(r.find(qn("w:noBreakHyphen")) is not None for r in nodes)
    assert has_no_break, "ожидался noBreakHyphen вместо обычного дефиса"


def test_inline_code_dashes_render_verbatim(document, config):
    """Inline-код — verbatim, без noBreakHyphen-сплита и без артефактов '- - -'."""
    from docx.oxml.ns import qn

    p = Paragraph(document, config)
    p.add_inline_nodes([ast.InlineCode(code="---")])
    runs = p.docx_paragraph._p.findall(qn("w:r"))
    has_no_break = any(r.find(qn("w:noBreakHyphen")) is not None for r in runs)
    assert not has_no_break, "inline-код не должен порождать noBreakHyphen"
    # Дефисы заменяются на U+2011 (non-breaking hyphen) — визуально такие же,
    # но без точки разрыва строки.
    assert "‑‑‑" in p.docx_paragraph.text


def test_inline_code_with_hyphen_text_is_single_literal(document, config):
    p = Paragraph(document, config)
    p.add_inline_nodes([ast.InlineCode(code="kebab-case-id")])
    expected = "kebab‑case‑id"
    code_runs = [r for r in p.docx_paragraph.runs if r.text and "‑" in r.text]
    assert any(r.text == expected for r in code_runs), (
        f"inline-код должен попасть в один run целиком (с U+2011 вместо '-'), "
        f"runs={[r.text for r in p.docx_paragraph.runs]}"
    )
