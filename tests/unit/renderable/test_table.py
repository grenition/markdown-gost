"""Юнит-тесты для :class:`markdown_gost.renderable.table.Table` (T013, native mode)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.base import RenderedInfo
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.table import Table


@pytest.fixture
def config():
    # Spacing занулено — иначе fixture добавит trailing spacer-параграф,
    # что ломает счётчики items в тестах рендера таблицы. Тесты на T013b spacer
    # используют отдельные конфиги с явным space_after. continuation_break
    # включён — manual-mode тесты в этом файле полагаются на ручной разрез
    # таблиц с подписью «Продолжение таблицы N».
    return load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  table:\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    continuation_break: true\n"
        "    table:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )


@pytest.fixture
def native_config():
    """Default без continuation_break — нативный режим (один <w:tbl>)."""

    return load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  table:\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    table:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )


@pytest.fixture
def document(config):
    return build_document(config)


@pytest.fixture
def layout():
    return LayoutState(max_height=Cm(20), max_width=Cm(15))


def _make_node(rows: list[list[str]]) -> ast.Table:
    """Простой helper: список строк с текстовыми ячейками → ast.Table."""

    table_rows: list[ast.TableRow] = []
    for idx, row_cells in enumerate(rows):
        cells = [
            ast.TableCell(children=[ast.Text(text=text)], header=(idx == 0))
            for text in row_cells
        ]
        table_rows.append(ast.TableRow(cells=cells, header=(idx == 0)))
    return ast.Table(rows=table_rows)


def _drain(table: Table, layout: LayoutState) -> list[RenderedInfo]:
    return [item for item in table.render(None, layout) if isinstance(item, RenderedInfo)]


def _spacing_attrs(paragraph):
    spacing = paragraph._p.find(qn("w:pPr") + "/" + qn("w:spacing"))
    assert spacing is not None
    return spacing


def test_native_mode_autofit_writes_content_based_widths(document, config, layout):
    """Без явных widths — autofit-режим, но gridCol заполнен content-based-оценкой.

    Без оценки LO рендерил бы равные колонки, что не соответствует ожиданиям
    пользователя — поэтому заполняем сами и держим w:type="autofit".
    """

    node = _make_node([["A", "B"], ["1", "2"], ["3", "4"]])
    table = Table(document, config, node, caption_text="Список")
    table.set_number(1)
    items = _drain(table, layout)
    # Ожидаем: caption + tbl
    assert len(items) == 2
    tbl = items[1].docx_element._element
    layout_el = tbl.find(qn("w:tblPr") + "/" + qn("w:tblLayout"))
    assert layout_el is not None
    assert layout_el.get(qn("w:type")) == "autofit"
    grid = tbl.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol"))
    assert len(cols) == 2
    widths = [int(c.get(qn("w:w"))) for c in cols]
    assert all(w > 0 for w in widths)


def test_autofit_widths_reflect_content_length(document, config, layout):
    """Колонка с длинным текстом получает заметно больше места, чем колонка с коротким."""

    node = _make_node(
        [
            ["№", "Длинное название компонента системы"],
            ["1", "Микроконтроллер"],
            ["2", "Стабилизатор LDO 3.3 В"],
        ]
    )
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    grid = tbl.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol"))
    widths = [int(c.get(qn("w:w"))) for c in cols]
    assert widths[1] > widths[0] * 3  # длинная колонка >> короткой


def test_explicit_widths_switch_to_fixed_layout(document, config, layout):
    node = _make_node([["A", "B", "C"], ["1", "2", "3"]])
    widths = [
        ast.Length(value=20.0, unit="%"),
        ast.Length(value=30.0, unit="%"),
        ast.Length(value=50.0, unit="%"),
    ]
    table = Table(document, config, node, caption_text=None, column_widths=widths)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    layout_el = tbl.find(qn("w:tblPr") + "/" + qn("w:tblLayout"))
    assert layout_el.get(qn("w:type")) == "fixed"
    grid = tbl.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol"))
    widths_dxa = [int(c.get(qn("w:w"))) for c in cols]
    assert all(w > 0 for w in widths_dxa)
    # Сумма ≈ полная ширина строки в dxa (default: A4 minus margins).
    total = sum(widths_dxa)
    assert total > 0
    # 20% + 30% + 50% == 100%, погрешность округления допустима в пределах ncols dxa.
    page_w = document.sections[0].page_width
    margins = document.sections[0].left_margin + document.sections[0].right_margin
    content_emu = int(page_w) - int(margins)
    expected_total = round(content_emu / 914400 * 1440)
    assert abs(total - expected_total) <= len(widths)


def test_mixed_auto_and_explicit_widths(document, config, layout):
    node = _make_node([["A", "B", "C"], ["1", "2", "3"]])
    widths = [
        ast.Length(value=3.0, unit="cm"),
        ast.Length(value=0.0, unit="auto"),
        ast.Length(value=0.0, unit="auto"),
    ]
    table = Table(document, config, node, column_widths=widths)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    grid = tbl.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol"))
    widths_dxa = [int(c.get(qn("w:w"))) for c in cols]
    # Первая колонка — 3cm, остальные две делят остаток поровну.
    assert widths_dxa[1] == widths_dxa[2]
    assert widths_dxa[0] != widths_dxa[1]


def test_explicit_row_heights_emit_trheight(document, config, layout):
    node = _make_node([["A", "B"], ["1", "2"], ["3", "4"]])
    heights = [
        ast.Length(value=0.0, unit="auto"),
        ast.Length(value=1.0, unit="cm"),
        ast.Length(value=0.0, unit="auto"),
    ]
    table = Table(document, config, node, row_heights=heights)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    rows = tbl.findall(qn("w:tr"))
    assert len(rows) == 3
    # Auto-строки — без trHeight.
    assert rows[0].find(qn("w:trPr") + "/" + qn("w:trHeight")) is None
    assert rows[2].find(qn("w:trPr") + "/" + qn("w:trHeight")) is None
    th = rows[1].find(qn("w:trPr") + "/" + qn("w:trHeight"))
    assert th is not None
    assert th.get(qn("w:hRule")) == "atLeast"
    assert int(th.get(qn("w:val"))) > 0


def test_measure_row_height_within_tolerance_for_arial(layout):
    """T013a: формула высоты строки должна быть в окне ``[real_pt; real_pt+8%]``.

    Эмпирически измеренная высота однострочной body-row для Arial 11pt × 1.15
    с шириной колонки 5cm (текст помещается в одну строку) в expected.pdf —
    20.50pt = 260350 EMU (мерилось локально на macOS-Arial).

    Старая формула ``× (body+pad) × 1.10`` давала пропорциональный запас,
    съедающий по 1-2 строки на странице на мелких шрифтах. Новая аддитивная
    формула (`body + cell_pad + 1.5pt border_safety`) физически константна.

    Верхняя граница ``+8%`` выбрана с запасом на cross-environment различие
    font metrics: на macOS freetype читает Arial напрямую (≈12pt line_height),
    в Docker/Linux Arial недоступен и `find_font` подставляет Liberation Sans —
    metrically совместимый с Arial по ширинам глифов, но с чуть бóльшей
    `face.size.height` (≈13pt). Разница ≈1pt стабильна и не масштабируется со
    шрифтом, поэтому реальная регрессия типа 1.10x (с пропорциональным +20%+
    на крупных шрифтах) всё равно ловится этим окном.
    """

    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  font:\n"
        "    family: Arial\n"
        "    size: 11pt\n"
        "    line_spacing: 1.15\n"
    )
    doc = build_document(cfg)
    # Body row из одной ячейки с коротким текстом — ширина 5cm гарантирует одну строку.
    node = ast.Table(
        rows=[
            ast.TableRow(
                cells=[ast.TableCell(children=[ast.Text(text="Реле")])]
            )
        ]
    )
    widths = [ast.Length(value=5.0, unit="cm")]
    table = Table(doc, cfg, node, column_widths=widths)
    table.set_number(1)

    body_rows = [r for r in table._rows if not r.is_header]
    assert body_rows, "expected at least one body row"
    real_pt = 20.50
    real_emu = int(real_pt * 12700)  # 260350
    measured = int(body_rows[0].height)
    # Нижняя граница: формула не должна недооценивать реальную высоту LO,
    # иначе LO сам будет резать наш chunk на стыке страниц.
    assert measured >= real_emu, (
        f"row height {measured / 12700:.2f}pt < real {real_pt}pt — "
        f"LO разрежет chunk сам"
    )
    # Верхняя граница: ≤ +8% (см. docstring — окно покрывает cross-env
    # разницу font metrics между macOS Arial и Linux Liberation Sans).
    upper = int(real_emu * 1.08)
    assert measured <= upper, (
        f"row height {measured / 12700:.2f}pt > {upper / 12700:.2f}pt "
        f"({(measured - real_emu) / real_emu * 100:.1f}% over real "
        f"{real_pt}pt) — формула слишком запаслива"
    )


def test_repeat_header_emits_tblheader_on_header_rows(document, native_config, layout):
    """Native режим — Word повторяет шапку через <w:tblHeader/>.

    В manual-режиме header дублируется нашим кодом, и tblHeader не пишется
    (см. отдельный тест).
    """

    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(document, native_config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    rows = tbl.findall(qn("w:tr"))
    header_marker = rows[0].find(qn("w:trPr") + "/" + qn("w:tblHeader"))
    body_marker = rows[1].find(qn("w:trPr") + "/" + qn("w:tblHeader"))
    assert header_marker is not None
    assert body_marker is None


def test_manual_mode_does_not_emit_tblheader(document, config, layout):
    """В manual-режиме мы дублируем шапку сами — Word не должен делать это поверх."""

    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    for row in tbl.findall(qn("w:tr")):
        assert row.find(qn("w:trPr") + "/" + qn("w:tblHeader")) is None


def test_header_bold_by_default(document, config, layout):
    """По умолчанию ``table.header_bold = true`` — runs шапки получают bold."""

    node = _make_node([["Hdr1", "Hdr2"], ["1", "2"]])
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    header_row = tbl.findall(qn("w:tr"))[0]
    bolds = header_row.findall(
        ".//" + qn("w:r") + "/" + qn("w:rPr") + "/" + qn("w:b")
    )
    assert len(bolds) == 2  # обе ячейки шапки


def test_header_not_bold_when_disabled(document, layout):
    """Override ``table.header_bold: false`` — bold не выставляется."""

    cfg = load_config_from_string(
        "preset: default\noverrides:\n  table:\n    header_bold: false\n"
    )
    doc = build_document(cfg)
    node = _make_node([["Hdr1", "Hdr2"], ["1", "2"]])
    table = Table(doc, cfg, node)
    table.set_number(1)
    layout = LayoutState(max_height=Cm(20), max_width=Cm(15))
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    header_row = tbl.findall(qn("w:tr"))[0]
    bolds = header_row.findall(
        ".//" + qn("w:r") + "/" + qn("w:rPr") + "/" + qn("w:b")
    )
    assert bolds == []


def test_font_size_not_applied_when_unset(document, config, layout):
    """По умолчанию ``table.font_size`` пуст — runs ячеек не получают w:sz override."""

    node = _make_node([["Hdr"], ["1"]])
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    sizes = tbl.findall(".//" + qn("w:r") + "/" + qn("w:rPr") + "/" + qn("w:sz"))
    assert sizes == []


def test_font_size_override_applied_to_cell_runs(layout):
    """Override ``table.font_size`` — каждый run ячейки получает w:sz=2*pt."""

    cfg = load_config_from_string(
        "preset: default\noverrides:\n  table:\n    font_size: 10pt\n"
    )
    doc = build_document(cfg)
    node = _make_node([["Hdr1", "Hdr2"], ["data1", "data2"]])
    table = Table(doc, cfg, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    sizes = tbl.findall(".//" + qn("w:r") + "/" + qn("w:rPr") + "/" + qn("w:sz"))
    # 4 ячейки × 1 run = 4 sz-элемента, все по 10pt (w:sz = half-points).
    assert len(sizes) == 4
    assert all(s.get(qn("w:val")) == "20" for s in sizes)


def test_cantsplit_set_on_every_row(document, config, layout):
    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    for row in tbl.findall(qn("w:tr")):
        assert row.find(qn("w:trPr") + "/" + qn("w:cantSplit")) is not None


def test_tbl_has_borders(document, config, layout):
    node = _make_node([["A"], ["1"]])
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[1].docx_element._element
    borders = tbl.find(qn("w:tblPr") + "/" + qn("w:tblBorders"))
    assert borders is not None
    sides = {child.tag for child in borders}
    assert qn("w:top") in sides
    assert qn("w:insideH") in sides
    assert qn("w:insideV") in sides


def test_caption_yielded_before_table(document, config, layout):
    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(document, config, node, caption_text="Список продуктов")
    table.set_number(7)
    items = _drain(table, layout)
    assert len(items) == 2
    cap_text = items[0].docx_element.text
    assert "Таблица 7" in cap_text
    assert "Список продуктов" in cap_text


def test_caption_without_text_no_dash(document, config, layout):
    node = _make_node([["A"], ["1"]])
    table = Table(document, config, node, caption_text=None)
    table.set_number(2)
    items = _drain(table, layout)
    cap_text = items[0].docx_element.text
    assert "Таблица 2" in cap_text
    assert not cap_text.rstrip().endswith("—")


def test_gost_table_caption_is_left_no_indent_single_spaced(layout):
    cfg = load_config_from_string("preset: gost-7-32-2017\n")
    doc = build_document(cfg)
    node = _make_node([["A"], ["1"]])
    table = Table(doc, cfg, node, caption_text="Очень длинное название таблицы")
    table.set_number(2)
    items = _drain(table, layout)
    cap_para = items[0].docx_element
    spacing = _spacing_attrs(cap_para)
    assert cap_para.text == "Таблица 2 — Очень длинное название таблицы"
    assert not cap_para.text.endswith(".")
    assert cap_para.alignment == WD_PARAGRAPH_ALIGNMENT.LEFT
    assert int(cap_para.paragraph_format.first_line_indent) == 0
    assert cap_para.paragraph_format.line_spacing == 1.0
    assert spacing.get(qn("w:line")) == "240"
    assert spacing.get(qn("w:lineRule")) == "auto"


def test_widths_count_mismatch_raises_at_construct(document, config):
    node = _make_node([["A", "B"], ["1", "2"]])
    with pytest.raises(ValueError, match="expected 2"):
        Table(
            document,
            config,
            node,
            column_widths=[ast.Length(value=50.0, unit="%")],
        )


def test_heights_count_mismatch_raises_at_construct(document, config):
    node = _make_node([["A", "B"], ["1", "2"], ["3", "4"]])
    with pytest.raises(ValueError, match="expected 3"):
        Table(
            document,
            config,
            node,
            row_heights=[ast.Length(value=1.0, unit="cm")],
        )


def test_explicit_widths_overflow_raises(document, config):
    """Если сумма явных колонок > content_width — ValueError на construct."""

    node = _make_node([["A", "B"], ["1", "2"]])
    # Оба значения по 25cm — намного больше ширины полосы.
    widths = [
        ast.Length(value=25.0, unit="cm"),
        ast.Length(value=0.0, unit="auto"),
    ]
    with pytest.raises(ValueError, match="reduce explicit values"):
        Table(document, config, node, column_widths=widths)


# ---- manual page-break (continuation_break) ------------------------------


def test_manual_mode_short_table_one_chunk(document, config, layout):
    """Короткая таблица в manual-режиме помещается одним чанком — без continuation."""

    node = _make_node([["A", "B"], ["1", "2"], ["3", "4"]])
    table = Table(document, config, node, caption_text="x")
    table.set_number(1)
    items = _drain(table, layout)
    # caption + одно tbl
    assert len(items) == 2
    # docx_table свойство в manual-режиме = None (нет «единой» таблицы)
    assert table.docx_table is None


def test_manual_mode_long_table_splits_with_continuation(document, config):
    """Длинная таблица в manual-режиме разрезается, между чанками — continuation paragraph."""

    rows = [["#", "Имя", "Описание"]]
    for i in range(40):
        rows.append([str(i + 1), f"Имя {i+1}", f"Описание элемента номер {i+1}"])
    node = _make_node(rows)
    table = Table(document, config, node, caption_text="Реестр")
    table.set_number(3)
    # Узкий layout, чтобы гарантированно случился разрез.
    layout = LayoutState(max_height=Cm(10), max_width=Cm(15))
    items = _drain(table, layout)
    # caption + хотя бы 2 tbl + хотя бы 1 continuation paragraph
    from docx.text.paragraph import Paragraph as DocxParagraph

    paragraphs = [it for it in items if isinstance(it.docx_element, DocxParagraph)]
    tables = [it for it in items if not isinstance(it.docx_element, DocxParagraph)]
    assert len(tables) >= 2  # таблица разрезана
    cont_paragraphs = [
        p for p in paragraphs if "Продолжение таблицы 3" in p.docx_element.text
    ]
    assert len(cont_paragraphs) == len(tables) - 1  # между каждым чанком


def test_manual_mode_continuation_uses_format_with_number(document, config):
    """Подпись «Продолжение таблицы N» содержит номер таблицы."""

    rows = [["A"]] + [[str(i)] for i in range(60)]
    node = _make_node(rows)
    table = Table(document, config, node)
    table.set_number(7)
    layout = LayoutState(max_height=Cm(8), max_width=Cm(10))
    items = _drain(table, layout)
    from docx.text.paragraph import Paragraph as DocxParagraph

    cont_texts = [
        it.docx_element.text
        for it in items
        if isinstance(it.docx_element, DocxParagraph)
        and "Продолжение" in it.docx_element.text
    ]
    assert cont_texts
    for text in cont_texts:
        assert "Продолжение таблицы 7" in text


def test_manual_mode_continuation_uses_appendix_display_number(document, config):
    rows = [["A"]] + [[str(i)] for i in range(60)]
    node = _make_node(rows)
    table = Table(document, config, node)
    table.set_number("А.1")
    layout = LayoutState(max_height=Cm(8), max_width=Cm(10))
    items = _drain(table, layout)
    from docx.text.paragraph import Paragraph as DocxParagraph

    cont_texts = [
        it.docx_element.text
        for it in items
        if isinstance(it.docx_element, DocxParagraph)
        and "Продолжение" in it.docx_element.text
    ]
    assert cont_texts
    assert all("Продолжение таблицы А.1" in text for text in cont_texts)


def test_manual_mode_repeats_header_in_each_chunk(document, config):
    """Каждый чанк начинается с дубликата строки шапки."""

    rows = [["№", "Имя"]] + [[str(i), f"x{i}"] for i in range(40)]
    node = _make_node(rows)
    table = Table(document, config, node)
    table.set_number(1)
    layout = LayoutState(max_height=Cm(10), max_width=Cm(15))
    items = _drain(table, layout)
    from docx.text.paragraph import Paragraph as DocxParagraph

    tables = [it for it in items if not isinstance(it.docx_element, DocxParagraph)]
    assert len(tables) >= 2
    # В каждой подтаблице первая строка содержит header (текст «№» / «Имя»).
    for tbl_info in tables:
        tbl_xml = tbl_info.docx_element._element
        first_tr = tbl_xml.findall(qn("w:tr"))[0]
        text = "".join(first_tr.itertext())
        assert "№" in text and "Имя" in text


def test_manual_mode_continuation_paragraph_has_page_break_before(document, config):
    """Continuation-параграф включает page_break_before — Word уйдёт на новую страницу."""

    rows = [["A"]] + [[str(i)] for i in range(40)]
    node = _make_node(rows)
    table = Table(document, config, node)
    table.set_number(1)
    layout = LayoutState(max_height=Cm(8), max_width=Cm(10))
    items = _drain(table, layout)
    from docx.text.paragraph import Paragraph as DocxParagraph

    cont = [
        it.docx_element
        for it in items
        if isinstance(it.docx_element, DocxParagraph)
        and "Продолжение" in it.docx_element.text
    ]
    assert cont
    for p in cont:
        assert p.paragraph_format.page_break_before is True


def test_manual_mode_continuation_uses_table_caption_style(layout):
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  captions:\n"
        "    continuation_break: true\n"
    )
    doc = build_document(cfg)
    rows = [["A"]] + [[str(i)] for i in range(40)]
    node = _make_node(rows)
    table = Table(doc, cfg, node)
    table.set_number(5)
    items = _drain(table, LayoutState(max_height=Cm(8), max_width=Cm(10)))

    from docx.text.paragraph import Paragraph as DocxParagraph

    cont = [
        it.docx_element
        for it in items
        if isinstance(it.docx_element, DocxParagraph)
        and "Продолжение таблицы 5" in it.docx_element.text
    ]
    assert cont
    for p in cont:
        spacing = _spacing_attrs(p)
        assert p.alignment == WD_PARAGRAPH_ALIGNMENT.LEFT
        assert int(p.paragraph_format.first_line_indent) == 0
        assert p.paragraph_format.line_spacing == 1.0
        assert spacing.get(qn("w:line")) == "240"
        assert spacing.get(qn("w:lineRule")) == "auto"


# ---- factory wiring -------------------------------------------------------


# ---- T013b block-spacing -------------------------------------------------


def test_space_after_emits_trailing_spacer(document, layout):
    """T013b: ``table.space_after`` → пустой spacer-параграф **после** таблицы.

    Spacer-параграф содержит ``<w:spacing w:before="<dxa>"/>`` (12pt → 240 dxa).
    """

    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  captions:\n    continuation_break: false\n"
        "  table:\n    space_after: 12pt\n"
    )
    doc = build_document(cfg)
    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(doc, cfg, node, caption_text="x")
    table.set_number(1)
    items = _drain(table, layout)
    # caption + tbl + spacer-параграф = 3 элемента
    assert len(items) == 3
    spacer = items[-1].docx_element
    from docx.text.paragraph import Paragraph as DocxParagraph

    assert isinstance(spacer, DocxParagraph)
    spacing = spacer._p.find(qn("w:pPr") + "/" + qn("w:spacing"))
    assert spacing is not None
    # 12pt = 240 dxa (twentieths of a point).
    assert int(spacing.get(qn("w:before"))) == 240


def test_no_spacer_when_space_after_zero(document, native_config, layout):
    """Default ``table.space_after = 0pt`` — spacer не эмитится (zero-cost)."""

    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(document, native_config, node, caption_text="x")
    table.set_number(1)
    items = _drain(table, layout)
    # Только caption + tbl, без trailing spacer.
    assert len(items) == 2


def test_space_before_applied_to_caption(document, layout):
    """T013b: ``table.space_before`` накладывается на caption-параграф."""

    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  captions:\n    continuation_break: false\n"
        "  table:\n    space_before: 18pt\n"
    )
    doc = build_document(cfg)
    node = _make_node([["A", "B"], ["1", "2"]])
    table = Table(doc, cfg, node, caption_text="x")
    table.set_number(1)
    items = _drain(table, layout)
    cap_para = items[0].docx_element
    # 18pt = Pt(18) = 228600 EMU
    assert int(cap_para.paragraph_format.space_before) == 228600


def test_manual_mode_spacer_only_after_last_chunk(document):
    """В manual-режиме trailing spacer эмитится **только** после последнего chunk'а.

    На промежуточных «Продолжение таблицы» spacer не должен появляться —
    иначе на стыке страниц будут лишние «дырки».
    """

    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  captions:\n    continuation_break: true\n"
        "  table:\n    space_after: 12pt\n"
    )
    doc = build_document(cfg)
    rows = [["#", "Имя", "Описание"]]
    for i in range(40):
        rows.append([str(i + 1), f"Имя {i+1}", f"Описание элемента номер {i+1}"])
    node = _make_node(rows)
    table = Table(doc, cfg, node, caption_text="Реестр")
    table.set_number(3)
    layout = LayoutState(max_height=Cm(10), max_width=Cm(15))
    items = _drain(table, layout)

    from docx.text.paragraph import Paragraph as DocxParagraph

    paragraphs = [it for it in items if isinstance(it.docx_element, DocxParagraph)]
    tables = [it for it in items if not isinstance(it.docx_element, DocxParagraph)]
    assert len(tables) >= 2  # таблица разрезана

    # Сколько spacer-параграфов?  Spacer = последний параграф, не содержит
    # «Продолжение». Должен быть ровно один (после последнего chunk'а).
    spacers = [
        p for p in paragraphs
        if "Продолжение" not in p.docx_element.text
        and "Таблица" not in p.docx_element.text
    ]
    assert len(spacers) == 1, (
        f"Ожидался ровно 1 spacer (после последнего chunk'а), получили {len(spacers)}"
    )


def test_factory_joins_caption_with_table(document, config):
    f = RenderableFactory(document, config, Numberer())
    table_ast = ast.Table(
        rows=[
            ast.TableRow(
                cells=[
                    ast.TableCell(children=[ast.Text(text="A")], header=True),
                    ast.TableCell(children=[ast.Text(text="B")], header=True),
                ],
                header=True,
            ),
            ast.TableRow(
                cells=[
                    ast.TableCell(children=[ast.Text(text="1")]),
                    ast.TableCell(children=[ast.Text(text="2")]),
                ]
            ),
        ]
    )
    cap = ast.Caption(target="table", text="Список", attrs={"widths": "30%, 70%"})
    rendered = f.create_all(ast.Document(children=[cap, table_ast]))
    assert len(rendered) == 1
    assert isinstance(rendered[0], Table)
    assert rendered[0]._is_fixed_layout  # widths переданы — fixed layout


def test_factory_table_without_caption(document, config):
    f = RenderableFactory(document, config, Numberer())
    table_ast = ast.Table(
        rows=[
            ast.TableRow(
                cells=[ast.TableCell(children=[ast.Text(text="A")], header=True)],
                header=True,
            ),
            ast.TableRow(cells=[ast.TableCell(children=[ast.Text(text="1")])]),
        ]
    )
    rendered = f.create_all(ast.Document(children=[table_ast]))
    assert len(rendered) == 1
    assert isinstance(rendered[0], Table)
    assert rendered[0]._caption_text is None


def test_factory_caption_widths_count_mismatch_raises(document, config):
    """Несовпадение числа widths с числом столбцов — ValueError на этапе фабрики."""

    f = RenderableFactory(document, config, Numberer())
    table_ast = ast.Table(
        rows=[
            ast.TableRow(
                cells=[
                    ast.TableCell(children=[ast.Text(text="A")], header=True),
                    ast.TableCell(children=[ast.Text(text="B")], header=True),
                    ast.TableCell(children=[ast.Text(text="C")], header=True),
                ],
                header=True,
            ),
        ]
    )
    cap = ast.Caption(target="table", text="x", attrs={"widths": "30%, 70%"})
    with pytest.raises(ValueError, match="widths: expected 3"):
        f.create_all(ast.Document(children=[cap, table_ast]))


# ---- T048: inline images in cells -----------------------------------------


def test_inline_image_in_cell_renders_drawing_not_text(document, config, layout):
    """T048: `![](logo.png)` в ячейке таблицы должен дать `w:drawing` в w:tc.

    До фикса Table создавал Paragraph без storage=, и _add_inline_image падал в
    no-storage fallback — рисовал курсивом `[logo.png]`. Тест проверяет, что
    после проброса storage в Table inline-картинка реально становится
    `<w:drawing>` внутри `<w:tc>`.
    """

    from markdown_gost.storage.fs import FilesystemStorage

    fixtures_dir = Path(__file__).parent / "_fixtures"
    storage = FilesystemStorage(base_dir=fixtures_dir)

    node = ast.Table(
        rows=[
            ast.TableRow(
                cells=[
                    ast.TableCell(
                        children=[ast.Image(src="sample.png", alt="")], header=False
                    ),
                    ast.TableCell(children=[ast.Text(text="x")], header=False),
                ],
                header=False,
            ),
        ]
    )
    table = Table(document, config, node, storage=storage)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[-1].docx_element._element
    tcs = tbl.findall(".//" + qn("w:tc"))
    assert len(tcs) == 2
    first_tc = tcs[0]
    drawings = first_tc.findall(".//" + qn("w:drawing"))
    assert drawings, "ожидался w:drawing в ячейке с inline-картинкой"
    # И никакого текстового fallback `[sample.png]` в этой ячейке быть не должно.
    texts = first_tc.findall(".//" + qn("w:t"))
    cell_text = "".join(t.text or "" for t in texts)
    assert "[" not in cell_text and "sample.png" not in cell_text


def test_inline_image_in_cell_without_storage_falls_back_to_text(
    document, config, layout
):
    """Если storage не задан (Table собран без storage=), сохраняем старое
    поведение: alt/src выводится как italic-текст. Это нужно, чтобы
    юнит-тесты, конструирующие Table напрямую без storage, не падали."""

    node = ast.Table(
        rows=[
            ast.TableRow(
                cells=[
                    ast.TableCell(
                        children=[ast.Image(src="logo.png", alt="")], header=False
                    ),
                ],
                header=False,
            ),
        ]
    )
    table = Table(document, config, node)
    table.set_number(1)
    items = _drain(table, layout)
    tbl = items[-1].docx_element._element
    tc = tbl.find(".//" + qn("w:tc"))
    assert tc is not None
    drawings = tc.findall(".//" + qn("w:drawing"))
    assert not drawings
    texts = tc.findall(".//" + qn("w:t"))
    cell_text = "".join(t.text or "" for t in texts)
    assert "logo.png" in cell_text


def test_factory_passes_storage_to_table(document, config):
    """RenderableFactory должна пробрасывать storage в Table, иначе картинки
    из импорта raw-HTML таблиц (T046) останутся текстом."""

    from markdown_gost.storage.fs import FilesystemStorage

    fixtures_dir = Path(__file__).parent / "_fixtures"
    storage = FilesystemStorage(base_dir=fixtures_dir)
    numberer = Numberer()
    factory = RenderableFactory(document, config, numberer, storage=storage)
    table_ast = ast.Table(
        rows=[
            ast.TableRow(
                cells=[
                    ast.TableCell(
                        children=[ast.Image(src="sample.png", alt="")], header=False
                    ),
                ],
                header=False,
            ),
        ]
    )
    renderables = factory.create_all(ast.Document(children=[table_ast]))
    table = next(r for r in renderables if isinstance(r, Table))
    table.set_number(1)
    items = _drain(table, LayoutState(max_height=Cm(20), max_width=Cm(15)))
    tbl = items[-1].docx_element._element
    drawings = tbl.findall(".//" + qn("w:drawing"))
    assert drawings, "factory должна передавать storage в Table"
