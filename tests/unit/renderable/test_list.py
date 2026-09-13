"""Юнит-тесты для :class:`markdown_gost.renderable.list.List`."""

from __future__ import annotations

import pytest
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.list import List


@pytest.fixture
def config():
    return load_config_from_string("preset: default\n")


@pytest.fixture
def document(config):
    return build_document(config)


def _layout_state(document) -> LayoutState:
    section = document.sections[0]
    max_width = section.page_width - section.left_margin - section.right_margin
    max_height = section.page_height - section.top_margin - section.bottom_margin
    return LayoutState(max_height=max_height, max_width=max_width)


def _flat_items(*texts: str, ordered: bool = False) -> ast.List:
    items = [
        ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text=t)])]) for t in texts
    ]
    return ast.List(ordered=ordered, start=1, items=items)


def _items(count: int) -> list[ast.ListItem]:
    return [
        ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text=f"item {n}")])])
        for n in range(1, count + 1)
    ]


def _render_paragraphs(lst: List, document) -> list[DocxParagraph]:
    state = _layout_state(document)
    out: list[DocxParagraph] = []
    for info in lst.render(None, state):
        out.append(info.docx_element)
    return out


def test_unordered_list_uses_bullet_marker_from_config(document, config):
    node = _flat_items("Первый", "Второй")
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    assert len(paragraphs) == 2
    for p, expected_text in zip(paragraphs, ["Первый", "Второй"], strict=True):
        # Маркер из конфига (по дефолту default — em-dash).
        assert p.text.startswith("—\t"), p.text
        assert expected_text in p.text


def test_ordered_list_renders_arabic_numbers(document, config):
    node = _flat_items("Раз", "Два", "Три", ordered=True)
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    assert texts[1].startswith("2.\t")
    assert texts[2].startswith("3.\t")


def test_multi_paragraph_item_renders_continuation_separately(document, config):
    """Если item содержит несколько ``ast.Paragraph``, второй и далее идут
    отдельными параграфами без маркера, выровненными по текстовой колонке."""
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="Первый абзац item-а")]),
            ast.Paragraph(children=[ast.Text(text="Continuation абзац")]),
        ]
    )
    item2 = ast.ListItem(
        children=[ast.Paragraph(children=[ast.Text(text="Второй item")])]
    )
    node = ast.List(ordered=True, start=1, items=[item, item2])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    assert len(paragraphs) == 3
    # Первый параграф — с маркером.
    assert paragraphs[0].text.startswith("1.\t")
    assert "Первый абзац item-а" in paragraphs[0].text
    # Continuation — БЕЗ маркера, но с тем же left_indent, без отрицательного
    # first_line_indent. Текст начинается сразу.
    assert not paragraphs[1].text.startswith("1.")
    assert not paragraphs[1].text.startswith("\t")
    assert paragraphs[1].text == "Continuation абзац"
    # Второй item — нумерация продолжается с 2.
    assert paragraphs[2].text.startswith("2.\t")
    assert "Второй item" in paragraphs[2].text


def test_multi_paragraph_continuation_alignment_matches_item_text(document, config):
    """Continuation-параграф выровнен по тексту item-а (left_indent = тот же,
    first_line_indent = 0)."""
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="head")]),
            ast.Paragraph(children=[ast.Text(text="cont")]),
        ]
    )
    node = ast.List(ordered=True, start=1, items=[item])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    head_pf = paragraphs[0].paragraph_format
    cont_pf = paragraphs[1].paragraph_format
    assert int(cont_pf.left_indent) == int(head_pf.left_indent)
    # У continuation первая строка не уезжает влево под маркер.
    assert (cont_pf.first_line_indent or 0) == 0


def test_multi_paragraph_with_interleaved_sublist_preserves_order(document, config):
    """Порядок: head para → sub-list → continuation para. Между ними не должно
    быть перестановок."""
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="head")]),
            ast.List(
                ordered=False,
                start=1,
                items=[
                    ast.ListItem(
                        children=[ast.Paragraph(children=[ast.Text(text="sub")])]
                    )
                ],
            ),
            ast.Paragraph(children=[ast.Text(text="tail")]),
        ]
    )
    node = ast.List(ordered=True, start=1, items=[item])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    assert "head" in texts[0]
    # Между head и tail должен быть как минимум один параграф с буллетом sub.
    bullet_idx = next(i for i, t in enumerate(texts) if "sub" in t)
    tail_idx = next(i for i, t in enumerate(texts) if t == "tail")
    assert 0 < bullet_idx < tail_idx


def test_ordered_list_paren_delimiter_renders_with_paren(document, config):
    """``ast.List(delimiter=")")`` — рендер выдаёт ``1)``, ``2)``, ``3)``."""
    items = [
        ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text=t)])])
        for t in ["A", "B", "C"]
    ]
    node = ast.List(ordered=True, start=1, items=items, delimiter=")")
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("1)\t")
    assert paragraphs[1].text.startswith("2)\t")
    assert paragraphs[2].text.startswith("3)\t")


def test_hierarchical_paren_marker_renders_with_paren(document, config):
    """Иерархический маркер с delimiter=``)`` — ``1.1)``, ``1.1.1)`` и т.д."""
    inner_inner = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[ast.Paragraph(children=[ast.Text(text="deep")])]
            )
        ],
        delimiter=")",
    )
    inner = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="mid")]),
                    inner_inner,
                ]
            )
        ],
        delimiter=")",
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="top")]),
                    inner,
                ]
            )
        ],
        delimiter=")",
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1)")
    assert "1.1)" in texts[1]
    assert "1.1.1)" in texts[2]


def test_ordered_list_respects_start_offset(document, config):
    node = _flat_items("a", "b", ordered=True)
    node.start = 5
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("5.\t")
    assert paragraphs[1].text.startswith("6.\t")


def test_md_delimiter_wins_over_numbered_format_config():
    """Литеральный delimiter из md (``ast.List.delimiter``) — источник истины
    для arabic-маркеров. Конфиг ``numbered_format`` для них больше не применяется."""
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  lists:\n    numbered_format: \"{n})\"\n"
    )
    doc = build_document(cfg)
    # AST с delimiter='.' (дефолт) — рендер должен выдать ``1.``, конфиг игнорируется.
    node_dot = _flat_items("a", "b", ordered=True)
    lst_dot = List(doc, cfg, node_dot)
    paragraphs_dot = _render_paragraphs(lst_dot, doc)
    assert paragraphs_dot[0].text.startswith("1.\t")
    # AST с delimiter=')' — рендер выдаёт ``1)``.
    node_paren = _flat_items("a", "b", ordered=True)
    node_paren.delimiter = ")"
    lst_paren = List(doc, cfg, node_paren)
    paragraphs_paren = _render_paragraphs(lst_paren, doc)
    assert paragraphs_paren[0].text.startswith("1)\t")


def test_bullet_marker_override():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  lists:\n    bullet_marker: \"•\"\n"
    )
    doc = build_document(cfg)
    node = _flat_items("a")
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    assert paragraphs[0].text.startswith("•\t")


def test_nested_unordered_list_indents_by_level(document, config):
    inner = _flat_items("вложенный")
    outer = ast.List(
        ordered=False,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="внешний")]),
                    inner,
                ]
            ),
        ],
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    assert len(paragraphs) == 2
    outer_indent = paragraphs[0].paragraph_format.left_indent
    inner_indent = paragraphs[1].paragraph_format.left_indent
    assert outer_indent is not None
    assert inner_indent is not None
    assert inner_indent > outer_indent


def test_nested_ordered_uses_hierarchical_path(document, config):
    """Nested ordered → иерархическая нумерация (1.1., 1.2., ...) по умолчанию.

    L1 разделён ``\\t`` (короткий маркер), L2 hierarchical → ``"  "`` (2 пробела),
    т.к. длинный маркер съедает таб в LibreOffice.
    """
    sub = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="y")])]),
        ],
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="A")]),
                    sub,
                ]
            ),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="B")])]),
        ],
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    # Подпункты внутри первого пункта — иерархические 1.1., 1.2.
    assert texts[1].startswith("1.1.  ")
    assert texts[2].startswith("1.2.  ")
    # Возврат на верхний уровень — продолжение нумерации L1.
    assert texts[3].startswith("2.\t")


def test_mixed_ordered_unordered_nested(document, config):
    bullet_sub = _flat_items("раз", "два")
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="A")]),
                    bullet_sub,
                ]
            ),
        ],
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    assert texts[1].startswith("—\t")
    assert texts[2].startswith("—\t")


def test_list_paragraphs_have_hanging_indent(document, config):
    node = _flat_items("a")
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    pf = paragraphs[0].paragraph_format
    assert pf.left_indent is not None
    # Висячий отступ — отрицательный first_line_indent.
    assert pf.first_line_indent is not None
    assert pf.first_line_indent < 0


def test_list_paragraph_xml_contains_marker_and_configured_indents():
    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  lists:\n"
        "    indent_left: 1.25cm\n"
        "    indent_per_level: 0.75cm\n"
    )
    doc = build_document(cfg)
    node = _flat_items("x")
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    paragraph = paragraphs[0]

    assert paragraph.text == "—\tx"
    ppr = paragraph._p.find(qn("w:pPr"))
    assert ppr is not None
    ind = ppr.find(qn("w:ind"))
    assert ind is not None
    assert ind.get(qn("w:left")) == "709"
    assert ind.get(qn("w:hanging")) == "425"
    tabs = ppr.find(qn("w:tabs"))
    assert tabs is not None
    tab = tabs.find(qn("w:tab"))
    assert tab is not None
    assert tab.get(qn("w:val")) == "left"
    assert tab.get(qn("w:pos")) == "709"
    num_pr = ppr.find(qn("w:numPr"))
    assert num_pr is not None
    num_id = num_pr.find(qn("w:numId"))
    assert num_id is not None
    assert num_id.get(qn("w:val")) == "0"


def test_indent_left_override_applied():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  lists:\n    indent_left: 3cm\n"
    )
    doc = build_document(cfg)
    node = _flat_items("a")
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    indent = paragraphs[0].paragraph_format.left_indent
    assert indent is not None
    assert abs(indent - Cm(3)) <= 5000


def test_list_factory_dispatch(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[_flat_items("a", "b")])
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], List)


def test_list_supports_four_levels_of_nesting(document, config):
    """AC: вложенность до 4 уровней — все уровни отрисовываются и имеют разный отступ."""

    def _wrap(text: str, sub: ast.List | None) -> ast.List:
        children: list[ast.Node] = [ast.Paragraph(children=[ast.Text(text=text)])]
        if sub is not None:
            children.append(sub)
        return ast.List(
            ordered=False,
            start=1,
            items=[ast.ListItem(children=children)],
        )

    l4 = _wrap("L4", None)
    l3 = _wrap("L3", l4)
    l2 = _wrap("L2", l3)
    l1 = _wrap("L1", l2)
    lst = List(document, config, l1)
    paragraphs = _render_paragraphs(lst, document)
    assert len(paragraphs) == 4
    indents = [p.paragraph_format.left_indent for p in paragraphs]
    assert all(i is not None for i in indents)
    assert indents[0] < indents[1] < indents[2] < indents[3]


def test_list_paragraph_marker_run_uses_normal_style(document, config):
    """Маркер не должен таскать форматирование из соседних inline."""
    node = ast.List(
        ordered=False,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Strong(children=[ast.Text(text="жирно")])]),
                ]
            )
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    runs = paragraphs[0].runs
    # Первый run — маркер с tab; он не должен быть жирным.
    marker_run = runs[0]
    assert marker_run.text.startswith("—") or marker_run.text.startswith("—")
    assert not marker_run.bold
    # А содержательный текст — жирный.
    assert any(r.bold and "жирно" in r.text for r in runs)


def test_alpha_marker_style_renders_russian_letters(document, config):
    """``marker_style='lower-alpha-ru'`` → ``а) б) в)`` по дефолтному формату."""
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="первый")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="второй")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="третий")])]),
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("а)\t")
    assert texts[1].startswith("б)\t")
    assert texts[2].startswith("в)\t")


def test_alpha_marker_style_russian_sequence_skips_forbidden_gost_letters(
    document, config
):
    """ГОСТ alpha-нумерация пропускает ``ё, з, й, о, ч, ъ, ы, ь``."""

    expected_letters = list("абвгдежиклмнпрстуфхцшщэюя")
    forbidden_letters = set("ёзйочъыь")
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=_items(len(expected_letters)),
    )

    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    markers = [p.text.split("\t", 1)[0] for p in paragraphs]

    assert markers == [f"{letter})" for letter in expected_letters]
    assert not any(marker[0] in forbidden_letters for marker in markers)


def test_alpha_marker_respects_start_offset(document, config):
    node = ast.List(
        ordered=True,
        start=3,  # начать с «в»
        marker_style="lower-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="y")])]),
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("в)\t")
    assert paragraphs[1].text.startswith("г)\t")


def test_alpha_format_override():
    cfg = load_config_from_string(
        "preset: default\noverrides:\n  lists:\n    alphabetic_format: \"{a}.\"\n"
    )
    doc = build_document(cfg)
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])]),
        ],
    )
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    assert paragraphs[0].text.startswith("а.\t")


def test_alpha_list_nested_under_arabic(document, config):
    """Alpha-список вложен в нумерованный список верхнего уровня."""
    alpha = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="alpha-1")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="alpha-2")])]),
        ],
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[
                    ast.Paragraph(children=[ast.Text(text="A")]),
                    alpha,
                ]
            ),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="B")])]),
        ],
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    assert texts[1].startswith("а)\t")
    assert texts[2].startswith("б)\t")
    assert texts[3].startswith("2.\t")
    # Alpha-уровень должен быть глубже по отступу.
    assert (
        paragraphs[1].paragraph_format.left_indent
        > paragraphs[0].paragraph_format.left_indent
    )


def test_alpha_marker_style_renders_english_lower(document, config):
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-en",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="one")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="two")])]),
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("a)\t")
    assert paragraphs[1].text.startswith("b)\t")


def test_alpha_marker_style_renders_english_upper(document, config):
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="upper-alpha-en",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="one")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="two")])]),
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("A)\t")
    assert paragraphs[1].text.startswith("B)\t")


def test_alpha_marker_style_renders_russian_upper(document, config):
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="upper-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="один")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="два")])]),
        ],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    assert paragraphs[0].text.startswith("А)\t")
    assert paragraphs[1].text.startswith("Б)\t")


def test_hierarchical_three_levels():
    """Три вложенных arabic-уровня → 1., 1.1., 1.1.1. (default behaviour, без флагов)."""
    cfg = load_config_from_string("preset: default\n")
    doc = build_document(cfg)

    def mk_item(text: str, sub: ast.List | None = None) -> ast.ListItem:
        children: list[ast.Node] = [ast.Paragraph(children=[ast.Text(text=text)])]
        if sub is not None:
            children.append(sub)
        return ast.ListItem(children=children)

    l3 = ast.List(ordered=True, start=1, items=[mk_item("L3")])
    l2 = ast.List(ordered=True, start=1, items=[mk_item("L2", l3)])
    l1 = ast.List(ordered=True, start=1, items=[mk_item("L1", l2)])

    lst = List(doc, cfg, l1)
    paragraphs = _render_paragraphs(lst, doc)
    # L1 — короткий маркер с табом; L>=2 — иерархический с 2 пробелами.
    assert paragraphs[0].text.startswith("1.\t")
    assert paragraphs[1].text.startswith("1.1.  ")
    assert paragraphs[2].text.startswith("1.1.1.  ")


def test_hierarchical_chain_breaks_under_non_arabic_parent():
    """Bullet/alpha в цепочке → глубже него нумерация снова локальная."""
    cfg = load_config_from_string("preset: default\n")
    doc = build_document(cfg)
    inner_ordered = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="y")])]),
        ],
    )
    bullet = ast.List(
        ordered=False,
        start=1,
        items=[
            ast.ListItem(
                children=[ast.Paragraph(children=[ast.Text(text="b")]), inner_ordered],
            )
        ],
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[ast.Paragraph(children=[ast.Text(text="A")]), bullet]
            )
        ],
    )
    lst = List(doc, cfg, outer)
    paragraphs = _render_paragraphs(lst, doc)
    texts = [p.text for p in paragraphs]
    # bullet рвёт цепочку → внутренний arabic нумеруется локально 1., 2.
    assert texts[0].startswith("1.\t")
    assert texts[2].startswith("1.\t")
    assert texts[3].startswith("2.\t")


def test_hierarchical_clamps_indent_at_5th_level():
    """L5 nesting → корректный маркер 1.1.1.1.1., но left_indent L4 == L5 (clamp на _MAX_LEVEL)."""
    cfg = load_config_from_string("preset: default\n")
    doc = build_document(cfg)

    def mk_item(text: str, sub: ast.List | None = None) -> ast.ListItem:
        children: list[ast.Node] = [ast.Paragraph(children=[ast.Text(text=text)])]
        if sub is not None:
            children.append(sub)
        return ast.ListItem(children=children)

    l5 = ast.List(ordered=True, start=1, items=[mk_item("L5")])
    l4 = ast.List(ordered=True, start=1, items=[mk_item("L4", l5)])
    l3 = ast.List(ordered=True, start=1, items=[mk_item("L3", l4)])
    l2 = ast.List(ordered=True, start=1, items=[mk_item("L2", l3)])
    l1 = ast.List(ordered=True, start=1, items=[mk_item("L1", l2)])

    lst = List(doc, cfg, l1)
    paragraphs = _render_paragraphs(lst, doc)
    # Маркеры — корректная иерархическая последовательность.
    expected_markers = ["1.", "1.1.", "1.1.1.", "1.1.1.1.", "1.1.1.1.1."]
    for p, marker in zip(paragraphs, expected_markers, strict=True):
        assert p.text.startswith(marker)
    indents = [p.paragraph_format.left_indent for p in paragraphs]
    assert indents[0] < indents[1] < indents[2] < indents[3]
    assert indents[3] == indents[4]


def test_l1_uses_tab_l2_hierarchical_uses_two_spaces():
    """L1 (`1.`) — короткий маркер с табом; L2 hierarchical (`1.1.`) — 2 пробела."""
    cfg = load_config_from_string("preset: default\n")
    doc = build_document(cfg)
    sub = ast.List(
        ordered=True,
        start=1,
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])])],
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(
                children=[ast.Paragraph(children=[ast.Text(text="A")]), sub]
            )
        ],
    )
    lst = List(doc, cfg, outer)
    paragraphs = _render_paragraphs(lst, doc)
    # L1
    assert "\t" in paragraphs[0].text
    assert paragraphs[0].text.startswith("1.\t")
    # L2 — без таба, с 2 пробелами после маркера.
    assert "\t" not in paragraphs[1].text
    assert paragraphs[1].text.startswith("1.1.  ")


def test_list_paragraph_has_no_w_numpr(document, config):
    """Inline-маркер должен исключать стилевую автонумерацию (w:numId=0)."""
    node = _flat_items("a", ordered=True)
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    ppr = paragraphs[0]._p.find(qn("w:pPr"))
    if ppr is None:
        return
    num_pr_list = ppr.findall(qn("w:numPr"))
    if not num_pr_list:
        return
    # Если numPr есть — numId должен быть 0 (отключение стилевой автонумерации).
    for num_pr in num_pr_list:
        num_id = num_pr.find(qn("w:numId"))
        if num_id is not None:
            assert num_id.get(qn("w:val")) == "0"
