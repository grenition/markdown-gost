"""Юнит-тесты для :class:`markdown_gost.renderable.equation.Equation` (T015).

Block-формула: 1×2 невидимая таблица — слева ``<m:oMath>`` с центром,
справа «(N)» с alignment по конфигу. Inline-формула: ``<m:oMath>``
встроен в run параграфа.
"""

from __future__ import annotations

import logging

import pytest
from docx.oxml.ns import qn
from docx.shared import Cm

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import RenderedInfo
from markdown_gost.renderable.equation import Equation

_OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_OMATH = f"{{{_OMML_NS}}}oMath"


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture
def config_no_parens():
    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  equation:\n"
        "    parentheses: false\n"
    )


@pytest.fixture
def config_left_align():
    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  equation:\n"
        "    numbering_alignment: left\n"
    )


@pytest.fixture
def config_equation_spacing():
    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  equation:\n"
        "    space_before: 6pt\n"
        "    space_after: 12pt\n"
    )


@pytest.fixture
def config_font_16pt():
    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  font:\n"
        "    size: 16pt\n"
    )


@pytest.fixture
def document(config):
    return build_document(config)


@pytest.fixture
def layout():
    return LayoutState(max_height=Cm(20), max_width=Cm(15))


def _drain(equation: Equation, layout: LayoutState) -> list[RenderedInfo]:
    return [
        item
        for item in equation.render(None, layout)
        if isinstance(item, RenderedInfo)
    ]


def _is_table(info: RenderedInfo) -> bool:
    el = getattr(info.docx_element, "_element", None)
    return el is not None and el.tag == qn("w:tbl")


def _content_row(tbl):
    rows = tbl.findall(qn("w:tr"))
    return rows[1] if len(rows) == 3 else rows[0]


# ---- структура таблицы ----------------------------------------------------


def test_block_equation_default_renders_one_content_row_without_spacing_rows(
    document, config, layout
):
    eq = Equation(document, config, ast.Equation(latex="a+b=c"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tables = [it for it in items if _is_table(it)]
    assert len(tables) == 1, items
    tbl = tables[0].docx_element._element
    rows = tbl.findall(qn("w:tr"))
    assert len(rows) == 1
    cells = rows[0].findall(qn("w:tc"))
    assert len(cells) == 2


def test_block_equation_left_cell_contains_omath(document, config, layout):
    """В левой ячейке параграф содержит ``<m:oMath>`` с математикой."""

    eq = Equation(document, config, ast.Equation(latex=r"\frac{a}{b}"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    left_cell = _content_row(tbl).findall(qn("w:tc"))[0]
    omath = left_cell.findall(".//" + _OMATH)
    assert omath, "ожидаем <m:oMath> в левой ячейке"


def test_left_cell_paragraph_centered(document, config, layout):
    eq = Equation(document, config, ast.Equation(latex="x=1"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    left_cell = _content_row(tbl).findall(qn("w:tc"))[0]
    p = left_cell.find(qn("w:p"))
    jc = p.find(qn("w:pPr") + "/" + qn("w:jc"))
    assert jc is not None
    assert jc.get(qn("w:val")) == "center"


def test_block_equation_spacing_rows_use_configured_heights(
    config_equation_spacing, layout
):
    document = build_document(config_equation_spacing)
    eq = Equation(document, config_equation_spacing, ast.Equation(latex="x=1"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    rows = tbl.findall(qn("w:tr"))
    assert len(rows) == 3

    before_height = rows[0].find(qn("w:trPr") + "/" + qn("w:trHeight"))
    content_height = rows[1].find(qn("w:trPr") + "/" + qn("w:trHeight"))
    after_height = rows[2].find(qn("w:trPr") + "/" + qn("w:trHeight"))

    assert before_height is not None
    assert before_height.get(qn("w:val")) == "120"
    assert before_height.get(qn("w:hRule")) == "exact"
    assert content_height is None
    assert after_height is not None
    assert after_height.get(qn("w:val")) == "240"
    assert after_height.get(qn("w:hRule")) == "exact"


def test_block_equation_spacing_rows_do_not_duplicate_formula_or_number(
    config_equation_spacing, layout
):
    document = build_document(config_equation_spacing)
    eq = Equation(document, config_equation_spacing, ast.Equation(latex="x=1"))
    eq.set_number(9)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    rows = tbl.findall(qn("w:tr"))

    for spacer_row in (rows[0], rows[2]):
        text = "".join(t.text or "" for t in spacer_row.findall(".//" + qn("w:t")))
        assert text == ""
        assert not spacer_row.findall(".//" + _OMATH)


# ---- нумерация в правой ячейке ------------------------------------------


def test_block_equation_right_cell_contains_parenthesised_number(
    document, config, layout
):
    eq = Equation(document, config, ast.Equation(latex="a=1"))
    eq.set_number(7)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    right_cell = _content_row(tbl).findall(qn("w:tc"))[1]
    text = "".join(t.text or "" for t in right_cell.findall(".//" + qn("w:t")))
    assert text == "(7)", text


def test_block_equation_right_cell_accepts_appendix_display_number(
    document, config, layout
):
    eq = Equation(document, config, ast.Equation(latex="a=1"))
    eq.set_number("А.1")
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    right_cell = _content_row(tbl).findall(qn("w:tc"))[1]
    text = "".join(t.text or "" for t in right_cell.findall(".//" + qn("w:t")))
    assert text == "(А.1)", text


def test_parentheses_disabled_yields_bare_number(config_no_parens, layout):
    document = build_document(config_no_parens)
    eq = Equation(document, config_no_parens, ast.Equation(latex="a=1"))
    eq.set_number(3)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    right_cell = _content_row(tbl).findall(qn("w:tc"))[1]
    text = "".join(t.text or "" for t in right_cell.findall(".//" + qn("w:t")))
    assert text == "3", text


def test_numbering_alignment_default_right(document, config, layout):
    eq = Equation(document, config, ast.Equation(latex="a"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    right_cell = _content_row(tbl).findall(qn("w:tc"))[1]
    p = right_cell.find(qn("w:p"))
    jc = p.find(qn("w:pPr") + "/" + qn("w:jc"))
    assert jc is not None
    assert jc.get(qn("w:val")) == "right"


def test_numbering_alignment_left_override(config_left_align, layout):
    document = build_document(config_left_align)
    eq = Equation(document, config_left_align, ast.Equation(latex="a"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    right_cell = _content_row(tbl).findall(qn("w:tc"))[1]
    p = right_cell.find(qn("w:p"))
    jc = p.find(qn("w:pPr") + "/" + qn("w:jc"))
    assert jc is not None
    assert jc.get(qn("w:val")) == "left"


# ---- borderless --------------------------------------------------------


def test_block_equation_table_has_invisible_borders(document, config, layout):
    """Чтобы вёрстка не показывала рамку вокруг формулы — все 6 направлений
    должны быть ``"none"`` (или ``"nil"``)."""

    eq = Equation(document, config, ast.Equation(latex="a"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element
    borders = tbl.find(qn("w:tblPr") + "/" + qn("w:tblBorders"))
    assert borders is not None
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = borders.find(qn(f"w:{side}"))
        assert b is not None
        assert b.get(qn("w:val")) in {"none", "nil"}, side


# ---- numbering category --------------------------------------------------


def test_equation_numbering_category(document, config):
    eq = Equation(document, config, ast.Equation(latex="x"))
    assert eq.numbering_category == "equation"


def test_block_equation_omml_runs_use_configured_font_size(
    config_font_16pt, layout
):
    document = build_document(config_font_16pt)
    eq = Equation(document, config_font_16pt, ast.Equation(latex=r"\frac{a}{b}=c"))
    eq.set_number(1)
    items = _drain(eq, layout)
    tbl = next(it for it in items if _is_table(it)).docx_element._element

    sizes = tbl.findall(".//" + qn("w:rPr") + "/" + qn("w:sz"))
    complex_sizes = tbl.findall(".//" + qn("w:rPr") + "/" + qn("w:szCs"))

    assert sizes
    assert complex_sizes
    assert {sz.get(qn("w:val")) for sz in sizes} == {"32"}
    assert {sz.get(qn("w:val")) for sz in complex_sizes} == {"32"}


# ---- error path ----------------------------------------------------------


def test_invalid_latex_renders_red_placeholder_paragraph(
    document, config, layout, caplog
):
    """Невалидный LaTeX → не падает, выдаёт красный курсивный плейсхолдер."""

    eq = Equation(document, config, ast.Equation(latex=r"\frac"))
    eq.set_number(1)
    with caplog.at_level(logging.WARNING):
        items = _drain(eq, layout)
    paragraphs = [
        it
        for it in items
        if getattr(it.docx_element, "_element", None) is not None
        and it.docx_element._element.tag == qn("w:p")
    ]
    assert paragraphs, items
    text = paragraphs[0].docx_element.text
    assert "Invalid equation" in text
    runs = paragraphs[0].docx_element._element.findall(qn("w:r"))
    color = runs[0].find(qn("w:rPr") + "/" + qn("w:color"))
    assert color is not None
    assert color.get(qn("w:val")).upper() == "C00000"
    assert any("equation" in rec.message.lower() for rec in caplog.records)


# ---- inline path (через Paragraph) ---------------------------------------


def test_inline_equation_emits_omath_in_paragraph(document, config):
    """``Paragraph.add_inline_nodes([InlineEquation])`` добавляет
    ``<m:oMath>`` внутрь параграфа."""

    from markdown_gost.renderable.paragraph import Paragraph

    para = Paragraph(document, config)
    para.add_inline_nodes([ast.InlineEquation(latex="x^2")])
    p = para.docx_paragraph._p
    omath = p.findall(".//" + _OMATH)
    assert omath, "ожидаем <m:oMath> внутри параграфа"


def test_inline_equation_invalid_latex_emits_red_placeholder_run(
    document, config, caplog
):
    from markdown_gost.renderable.paragraph import Paragraph

    para = Paragraph(document, config)
    with caplog.at_level(logging.WARNING):
        para.add_inline_nodes([ast.InlineEquation(latex=r"\frac")])
    p = para.docx_paragraph._p
    runs = p.findall(qn("w:r"))
    assert runs, "ожидаем хотя бы один run-плейсхолдер"
    rpr = runs[0].find(qn("w:rPr"))
    assert rpr is not None
    assert rpr.find(qn("w:i")) is not None
    color = rpr.find(qn("w:color"))
    assert color is not None and color.get(qn("w:val")).upper() == "C00000"
    text = "".join(t.text or "" for t in runs[0].findall(qn("w:t")))
    assert "invalid" in text.lower()
    assert any("equation" in rec.message.lower() for rec in caplog.records)
