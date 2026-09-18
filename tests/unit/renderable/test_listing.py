"""Юнит-тесты для :class:`markdown_gost.renderable.listing.Listing` (T014)."""

from __future__ import annotations

import pytest
from docx.oxml.ns import qn
from docx.shared import Cm

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import RenderedInfo
from markdown_gost.renderable.listing import Listing


@pytest.fixture
def manual_config():
    """captions.continuation_break = true — ручной разрез с подписью «Продолжение»."""

    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  listing:\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    continuation_break: true\n"
        "    listing:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )


@pytest.fixture
def native_config():
    """Default (continuation_break = false) — один <w:tbl>, Word ломает сам."""

    return load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  listing:\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    listing:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )


@pytest.fixture
def document(manual_config):
    return build_document(manual_config)


@pytest.fixture
def native_document(native_config):
    return build_document(native_config)


@pytest.fixture
def layout():
    return LayoutState(max_height=Cm(20), max_width=Cm(15))


def _drain(listing: Listing, layout: LayoutState) -> list[RenderedInfo]:
    return [
        item
        for item in listing.render(None, layout)
        if isinstance(item, RenderedInfo)
    ]


def _is_table(info: RenderedInfo) -> bool:
    el = getattr(info.docx_element, "_element", None)
    return el is not None and el.tag == qn("w:tbl")


def _is_paragraph(info: RenderedInfo) -> bool:
    el = getattr(info.docx_element, "_element", None)
    return el is not None and el.tag == qn("w:p")


# ---- caption + базовая структура --------------------------------------


def test_caption_before_listing_with_number_and_text(document, manual_config, layout):
    node = ast.Listing(language="python", code="print(1)\n")
    listing = Listing(document, manual_config, node, caption_text="Сортировка")
    listing.set_number(3)
    items = _drain(listing, layout)
    # Первый элемент — параграф подписи
    assert _is_paragraph(items[0])
    caption_text = items[0].docx_element.text
    assert "Листинг" in caption_text
    assert "3" in caption_text
    assert "Сортировка" in caption_text
    # Далее — таблица с кодом
    assert any(_is_table(it) for it in items[1:])


def test_caption_without_text_drops_trailing_dash(document, manual_config, layout):
    # Подпись без текста на уровне AST → caption_text="" (пустая строка, но подпись
    # есть, поэтому листинг нумеруется).
    node = ast.Listing(language=None, code="x = 1\n")
    listing = Listing(document, manual_config, node, caption_text="")
    listing.set_number(1)
    items = _drain(listing, layout)
    caption_text = items[0].docx_element.text
    # Висячий разделитель «— » при пустой подписи срезается Caption
    assert caption_text.rstrip().endswith("1")


def test_bare_listing_has_no_caption_and_opts_out_of_numbering(
    document, manual_config, layout
):
    """Голый ``` без подписи — нулевая ``numbering_category``."""

    node = ast.Listing(language=None, code="x = 1\n")
    listing = Listing(document, manual_config, node, caption_text=None)
    # Opt-out из нумерации: пустая категория сигнализирует Renderer'у
    # «не зови numberer».
    assert listing.numbering_category == ""
    items = _drain(listing, layout)
    # Никаких параграфов «Листинг N» в выдаче — только таблица + хвостовой
    # spacer (и возможный continuation в manual-режиме, но в bare его не
    # должно быть).
    paragraphs = [it for it in items if _is_paragraph(it)]
    for p in paragraphs:
        assert "Листинг" not in p.docx_element.text
    # И ровно одна таблица — ни manual-чанков, ни continuation-параграфов.
    tables = [it for it in items if _is_table(it)]
    assert len(tables) == 1


# ---- режим manual: один короткий листинг = одна таблица ---------------


def test_manual_short_listing_emits_single_table(document, manual_config, layout):
    code = "\n".join(f"print({i})" for i in range(3)) + "\n"
    node = ast.Listing(language="python", code=code)
    listing = Listing(document, manual_config, node, caption_text="Кратко")
    listing.set_number(1)
    items = _drain(listing, layout)
    tables = [it for it in items if _is_table(it)]
    assert len(tables) == 1
    # Внутри таблицы — 3 параграфа-строки в единственной ячейке
    tc = tables[0].docx_element._element.find(
        qn("w:tr") + "/" + qn("w:tc")
    )
    assert tc is not None
    paragraphs = tc.findall(qn("w:p"))
    assert len(paragraphs) == 3


def test_manual_long_listing_breaks_into_chunks(manual_config):
    """Очень длинный листинг → несколько таблиц, между ними подпись «Продолжение»."""

    document = build_document(manual_config)
    # Узкий layout: 8 строк на странице — гарантирует, что 30-строчный
    # листинг порежется как минимум на 3 чанка.
    layout = LayoutState(max_height=Cm(5), max_width=Cm(15))
    code = "\n".join(f"line_{i:02d} = {i}" for i in range(30)) + "\n"
    node = ast.Listing(language="python", code=code)
    listing = Listing(document, manual_config, node, caption_text="Длинный")
    listing.set_number(2)
    items = _drain(listing, layout)
    tables = [it for it in items if _is_table(it)]
    # Ожидаем несколько чанков (как минимум 2).
    assert len(tables) >= 2
    # Между чанками — параграфы «Продолжение листинга 2».
    cont_paragraphs = [
        it
        for it in items
        if _is_paragraph(it)
        and "Продолжение листинга 2" in it.docx_element.text
    ]
    # На N чанков ожидаем N-1 continuation-параграфов.
    assert len(cont_paragraphs) == len(tables) - 1
    # Все параграфы продолжения должны иметь page_break_before.
    for cont in cont_paragraphs:
        pf = cont.docx_element.paragraph_format
        assert pf.page_break_before is True


# ---- режим native: один сплошной <w:tbl> -----------------------------


def test_native_mode_single_table_with_all_lines(native_document, native_config):
    layout = LayoutState(max_height=Cm(5), max_width=Cm(15))
    code = "\n".join(f"line_{i}" for i in range(20)) + "\n"
    node = ast.Listing(language=None, code=code)
    listing = Listing(native_document, native_config, node, caption_text="N")
    listing.set_number(1)
    items = _drain(listing, layout)
    tables = [it for it in items if _is_table(it)]
    # native — ровно одна таблица, независимо от длины кода.
    assert len(tables) == 1
    tc = tables[0].docx_element._element.find(
        qn("w:tr") + "/" + qn("w:tc")
    )
    assert tc is not None
    paragraphs = tc.findall(qn("w:p"))
    assert len(paragraphs) == 20
    # Никаких «Продолжение листинга» в native-режиме быть не должно.
    cont = [
        it
        for it in items
        if _is_paragraph(it)
        and "Продолжение листинга" in it.docx_element.text
    ]
    assert cont == []


# ---- шрифт + line spacing из конфига ---------------------------------


def test_listing_paragraph_uses_configured_mono_font(document, manual_config, layout):
    node = ast.Listing(language=None, code="hello\n")
    listing = Listing(document, manual_config, node)
    listing.set_number(1)
    items = _drain(listing, layout)
    table = next(it for it in items if _is_table(it))
    tc = table.docx_element._element.find(qn("w:tr") + "/" + qn("w:tc"))
    p = tc.find(qn("w:p"))
    runs = p.findall(qn("w:r"))
    assert runs, "ожидаем хотя бы один run"
    # Первый run должен ссылаться на сконфигурированный font + size.
    rfonts = runs[0].find(qn("w:rPr") + "/" + qn("w:rFonts"))
    sz = runs[0].find(qn("w:rPr") + "/" + qn("w:sz"))
    assert rfonts is not None
    assert rfonts.get(qn("w:ascii")) == manual_config.listing.font.family
    # Размер задан в half-points: 12pt → "24"
    assert sz is not None
    assert sz.get(qn("w:val")) == "24"


# ---- подсветка: pygments runs --------------------------------------


def test_syntax_highlighting_emits_styled_runs():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  listing:\n"
        "    syntax_highlighting: true\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    listing:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )
    document = build_document(cfg)
    layout = LayoutState(max_height=Cm(20), max_width=Cm(15))
    node = ast.Listing(
        language="python",
        code='def f():\n    return "hi"\n',
    )
    listing = Listing(document, cfg, node, caption_text="Highlighted")
    listing.set_number(1)
    items = _drain(listing, layout)
    table = next(it for it in items if _is_table(it))
    runs = table.docx_element._element.findall(
        qn("w:tr") + "/" + qn("w:tc") + "/" + qn("w:p") + "/" + qn("w:r")
    )
    # При подсветке runs больше одного (ключевое слово / идентификатор / строка
    # должны попасть в разные runs).
    assert len(runs) > 2
    # Хотя бы один run должен иметь явный цвет (rPr/color).
    colored = [
        r
        for r in runs
        if r.find(qn("w:rPr") + "/" + qn("w:color")) is not None
    ]
    assert colored, "ожидаем подсвеченные runs"


def test_unknown_language_falls_back_to_monochrome():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  listing:\n"
        "    syntax_highlighting: true\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    listing:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )
    document = build_document(cfg)
    layout = LayoutState(max_height=Cm(20), max_width=Cm(15))
    node = ast.Listing(language="totally-unknown-lang", code="line one\nline two\n")
    listing = Listing(document, cfg, node)
    listing.set_number(1)
    items = _drain(listing, layout)
    table = next(it for it in items if _is_table(it))
    # Без падения — должны получить две монохромные строки.
    paragraphs = table.docx_element._element.findall(
        qn("w:tr") + "/" + qn("w:tc") + "/" + qn("w:p")
    )
    assert len(paragraphs) == 2


def test_no_language_skips_pygments():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  listing:\n"
        "    syntax_highlighting: true\n"
        "    space_before: 0pt\n"
        "    space_after: 0pt\n"
        "  captions:\n"
        "    listing:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )
    document = build_document(cfg)
    layout = LayoutState(max_height=Cm(20), max_width=Cm(15))
    node = ast.Listing(language=None, code="abc\ndef\n")
    listing = Listing(document, cfg, node)
    listing.set_number(1)
    items = _drain(listing, layout)
    table = next(it for it in items if _is_table(it))
    # Без языка подсветка не активируется — runs цвета быть не должно.
    runs = table.docx_element._element.findall(
        qn("w:tr") + "/" + qn("w:tc") + "/" + qn("w:p") + "/" + qn("w:r")
    )
    colored = [r for r in runs if r.find(qn("w:rPr") + "/" + qn("w:color")) is not None]
    assert not colored


# ---- borders / wrapper -----------------------------------------------


def test_listing_table_has_visible_borders(document, manual_config, layout):
    node = ast.Listing(language=None, code="x\n")
    listing = Listing(document, manual_config, node)
    listing.set_number(1)
    items = _drain(listing, layout)
    table = next(it for it in items if _is_table(it))
    tbl_borders = table.docx_element._element.find(
        qn("w:tblPr") + "/" + qn("w:tblBorders")
    )
    assert tbl_borders is not None
    # Все 6 направлений должны быть `single`.
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = tbl_borders.find(qn(f"w:{side}"))
        assert b is not None
        assert b.get(qn("w:val")) == "single"
