"""Юнит-тесты для :class:`markdown_gost.renderable.heading.Heading`."""

from __future__ import annotations

import pytest
from docx.oxml.ns import qn
from docx.shared import Length

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.heading import Heading


@pytest.fixture
def config():
    return load_config_from_string("preset: default\n")


@pytest.fixture
def document(config):
    return build_document(config)


def _make(document, config, numberer, level: int, text: str, numbered: bool = True) -> Heading:
    node = ast.Heading(level=level, numbered=numbered, children=[ast.Text(text=text)])
    return Heading(document, config, node, numberer)


def test_level_sets_paragraph_style(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "Глава")
    assert h.docx_paragraph.style.name == "Heading 1"
    assert h.level == 1


def test_invalid_level_raises(document, config):
    n = Numberer()
    with pytest.raises(ValueError):
        _make(document, config, n, 7, "слишком глубокий")


def test_multilevel_numbering_sequence(document, config):
    """h1; h2; h3; h2; h1; h2 → '1'; '1.1'; '1.1.1'; '1.2'; '2'; '2.1'."""
    n = Numberer()
    sequence = [(1, "1"), (2, "1.1"), (3, "1.1.1"), (2, "1.2"), (1, "2"), (2, "2.1")]
    for level, expected in sequence:
        h = _make(document, config, n, level, "Glava")
        assert h.docx_paragraph.text.startswith(expected), (
            f"level={level} expected prefix {expected!r}, got {h.docx_paragraph.text!r}"
        )


def test_unnumbered_heading_does_not_inject_prefix(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "Аннотация", numbered=False)
    assert not h.docx_paragraph.text.startswith("1")
    assert "Аннотация" in h.docx_paragraph.text
    # Счётчик уровня бампается даже для ненумерованного — заголовок занимает
    # полноценный слот в иерархии (нужно для корректной нумерации подзаголовков).
    assert n.heading_prefix_at(1) == "1"


def test_unnumbered_heading_bumps_counter_for_subheadings(document, config):
    """Подзаголовки под ``#*`` должны получать его как родителя.

    Без бампа счётчика ``## Sub`` после ``#* Title`` нумеровался бы как
    ``0.1`` — баг, заголовок ``#*`` должен быть полноценным родителем.
    """
    n = Numberer()
    _make(document, config, n, 1, "Аннотация", numbered=False)
    h_sub = _make(document, config, n, 2, "Подраздел")
    assert h_sub.docx_paragraph.text.startswith("1.1 "), h_sub.docx_paragraph.text


def test_unnumbered_heading_occupies_numbering_slot(document, config):
    """``#*`` занимает полноценный слот, последующие нумерованные сдвигаются."""
    n = Numberer()
    _make(document, config, n, 1, "Глава 1")  # "1"
    h_unnumbered = _make(document, config, n, 1, "Аннотация", numbered=False)
    h_after = _make(document, config, n, 1, "Глава 2")
    assert not h_unnumbered.docx_paragraph.text[:1].isdigit()
    assert "Аннотация" in h_unnumbered.docx_paragraph.text
    # `#*` занял слот #2, следующий нумерованный — это уже #3.
    assert h_after.docx_paragraph.text.startswith("3 "), h_after.docx_paragraph.text


def test_unnumbered_heading_strips_numpr(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "Аннотация", numbered=False)
    ppr = h.docx_paragraph._p.find(qn("w:pPr"))
    assert ppr is not None
    numpr_elements = ppr.findall(qn("w:numPr"))
    assert len(numpr_elements) >= 1
    numid = numpr_elements[-1].find(qn("w:numId"))
    assert numid is not None
    assert numid.get(qn("w:val")) == "0"


def test_numbered_heading_strips_inherited_numpr(document, config):
    """Manual prefix не должен дублироваться стилевой автонумерацией.

    Стили Heading 1..6 в base.docx содержат собственный <w:numPr>. При
    добавлении manual prefix мы должны заглушить стилевую нумерацию,
    иначе на экране получим '1     1 ВВЕДЕНИЕ'.
    """
    n = Numberer()
    h = _make(document, config, n, 1, "ВВЕДЕНИЕ")
    ppr = h.docx_paragraph._p.find(qn("w:pPr"))
    assert ppr is not None
    numpr_elements = ppr.findall(qn("w:numPr"))
    # Параграф должен иметь явный numPr с numId=0, чтобы перебить стилевой.
    assert numpr_elements, "ожидался override <w:numPr> в pPr нумерованного заголовка"
    numid = numpr_elements[-1].find(qn("w:numId"))
    assert numid is not None
    assert numid.get(qn("w:val")) == "0"


def test_numbered_heading_text_has_prefix_exactly_once(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "ВВЕДЕНИЕ")
    text = h.docx_paragraph.text
    # Текст параграфа должен начинаться с "1 " (manual prefix), и "1" внутри
    # допускается только один раз — стилевой автодубль исключён.
    assert text.startswith("1 "), f"expected leading '1 ' prefix, got {text!r}"
    assert text.count("1") == 1, f"prefix '1' duplicated: {text!r}"


def test_numbered_h2_has_dotted_prefix_no_duplicate(document, config):
    n = Numberer()
    _make(document, config, n, 1, "Глава")  # bumps level 1 → "1"
    h2 = _make(document, config, n, 2, "Цели")
    text = h2.docx_paragraph.text
    assert text.startswith("1.1 "), f"expected '1.1 ' prefix, got {text!r}"
    # Никаких '1.1' дважды (стилевой автонумерации быть не должно).
    assert text.count("1.1") == 1


def test_numbering_none_strips_numpr_and_no_prefix(document):
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  headings:\n    numbering: none\n"
    )
    doc = build_document(cfg)
    n = Numberer()
    node = ast.Heading(level=1, numbered=True, children=[ast.Text(text="ВВЕДЕНИЕ")])
    h = Heading(doc, cfg, node, n)
    text = h.docx_paragraph.text
    assert "ВВЕДЕНИЕ" in text
    # Не должно быть числового префикса.
    assert not text.lstrip().startswith(("1", "2", "3"))
    ppr = h.docx_paragraph._p.find(qn("w:pPr"))
    assert ppr is not None
    numpr_elements = ppr.findall(qn("w:numPr"))
    assert numpr_elements
    numid = numpr_elements[-1].find(qn("w:numId"))
    assert numid is not None
    assert numid.get(qn("w:val")) == "0"


def test_structural_h1_uses_dedicated_style_without_number_or_numpr(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "ВВЕДЕНИЕ", numbered=False)

    assert h.docx_paragraph.style.name == "MD2GOST Structural Heading"
    assert h.docx_paragraph.text == "ВВЕДЕНИЕ"
    assert h.number is None
    assert n.heading_prefix_at(1) == "0"
    assert h.is_numbered is False

    ppr = h.docx_paragraph._p.find(qn("w:pPr"))
    assert ppr is None or ppr.find(qn("w:numPr")) is None


def test_structural_h1_does_not_bump_numbered_h1(document, config):
    n = Numberer()
    structural = _make(document, config, n, 1, "ЗАКЛЮЧЕНИЕ", numbered=False)
    after = _make(document, config, n, 1, "Основная часть")

    assert structural.number is None
    assert after.docx_paragraph.text.startswith("1 "), after.docx_paragraph.text


def test_structural_titles_are_matched_case_insensitively(document, config):
    n = Numberer()
    h = _make(document, config, n, 1, "список использованных источников", numbered=False)

    assert h.docx_paragraph.style.name == "MD2GOST Structural Heading"
    assert n.heading_prefix_at(1) == "0"


def test_unnumbered_h2_keeps_legacy_numbering_slot(document, config):
    n = Numberer()
    _make(document, config, n, 1, "Глава")
    h = _make(document, config, n, 2, "Без номера", numbered=False)
    after = _make(document, config, n, 2, "Следующий")

    assert h.docx_paragraph.style.name == "Heading 2"
    assert h.number is None
    assert after.docx_paragraph.text.startswith("1.2 "), after.docx_paragraph.text


def test_numbered_h1_page_break_uses_level_config(document):
    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  headings:\n"
        "    levels:\n"
        "      1:\n"
        "        page_break_before: false\n"
    )
    doc = build_document(cfg)
    h = _make(doc, cfg, Numberer(), 1, "Глава")

    list(h.render(None, LayoutState(Length(10_000_000), Length(6_000_000))))

    assert h.docx_paragraph.paragraph_format.page_break_before is False


def test_numbered_h1_page_breaks_when_page_already_has_content(document, config):
    h = _make(document, config, Numberer(), 1, "Глава")
    state = LayoutState(Length(10_000_000), Length(6_000_000))
    state.add_height(Length(100_000))

    list(h.render(None, state))

    assert h.docx_paragraph.paragraph_format.page_break_before is True


def test_appendix_heading_does_not_force_extra_page_break(document, config):
    n = Numberer()
    n.start_appendix("А")
    h = _make(document, config, n, 1, "Раздел приложения")
    state = LayoutState(Length(10_000_000), Length(6_000_000))
    state.add_height(Length(100_000))

    list(h.render(None, state))

    assert h.docx_paragraph.paragraph_format.page_break_before is False


def test_structural_h1_page_break_uses_structural_config(document):
    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  headings:\n"
        "    structural:\n"
        "      page_break_before: false\n"
    )
    doc = build_document(cfg)
    h = _make(doc, cfg, Numberer(), 1, "ВВЕДЕНИЕ", numbered=False)

    list(h.render(None, LayoutState(Length(10_000_000), Length(6_000_000))))

    assert h.docx_paragraph.paragraph_format.page_break_before is False
