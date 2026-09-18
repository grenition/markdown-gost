"""Юнит-тесты для :class:`markdown_gost.renderable.list.List`.

Нативный режим (``lists.mode: native``, дефолт): bullet/arabic списки
рендерятся нумерацией Word — параграф несёт ``w:numPr``, форматы маркеров и
геометрия живут в ``numbering.xml``. Буквенные списки (``а)``) и режим
``inline`` остаются на литеральных маркерах (ГОСТ запрещает буквы
ё, з, й, о, ч, ъ, ы, ь — нумерация Word такой фильтр не выражает).
"""

from __future__ import annotations

import pytest
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.config.units import parse_length
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.list import List

# 1.25cm / 0.75cm в твипах (округление Length.twips).
_LEFT_TW = "709"
_PER_LEVEL_TW = "425"
_LEFT_L2_TW = "1134"  # 709 + 425


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture
def document(config):
    return build_document(config)


def _layout_state(document) -> LayoutState:
    section = document.sections[0]
    max_width = section.page_width - section.left_margin - section.right_margin
    max_height = section.page_height - section.top_margin - section.bottom_margin
    return LayoutState(max_height=max_height, max_width=max_width)


def _flat_items(*texts: str, ordered: bool = False) -> ast.List:
    items = [ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text=t)])]) for t in texts]
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


# ---Helpers для доступа к numbering.xml---


def _numbering_root(document):
    """Корень numbering.xml или None, если часть не создана."""
    try:
        part = document.part.part_related_by(RT.NUMBERING)
    except KeyError:
        return None
    return parse_xml(part.blob)


def _numpr(p: DocxParagraph) -> tuple[int, int] | None:
    """``(ilvl, numId)`` из pPr параграфа, либо None."""
    ppr = p._p.find(qn("w:pPr"))
    if ppr is None:
        return None
    num_pr = ppr.find(qn("w:numPr"))
    if num_pr is None:
        return None
    ilvl = num_pr.find(qn("w:ilvl"))
    num_id = num_pr.find(qn("w:numId"))
    assert ilvl is not None and num_id is not None
    return (int(ilvl.get(qn("w:val"))), int(num_id.get(qn("w:val"))))


def _num_el(root, num_id: int):
    for num in root.findall(qn("w:num")):
        if int(num.get(qn("w:numId"))) == num_id:
            return num
    raise AssertionError(f"w:num {num_id} не найден")


def _abstract(root, num_id: int):
    num = _num_el(root, num_id)
    ref = num.find(qn("w:abstractNumId"))
    assert ref is not None
    aid = int(ref.get(qn("w:val")))
    for abstract in root.findall(qn("w:abstractNum")):
        if int(abstract.get(qn("w:abstractNumId"))) == aid:
            return abstract
    raise AssertionError(f"abstractNum {aid} не найден")


def _lvl(abstract, ilvl: int):
    for lvl in abstract.findall(qn("w:lvl")):
        if int(lvl.get(qn("w:ilvl"))) == ilvl:
            return lvl
    raise AssertionError(f"ilvl {ilvl} не найден")


def _field(el, tag: str) -> str:
    child = el.find(qn(tag))
    assert child is not None, f"{tag} не найден"
    return child.get(qn("w:val"))


def _ind(lvl) -> tuple[str, str]:
    ppr = lvl.find(qn("w:pPr"))
    assert ppr is not None
    ind = ppr.find(qn("w:ind"))
    assert ind is not None
    return (ind.get(qn("w:left")), ind.get(qn("w:hanging")))


def _nest(text: str, sub: ast.List | None, *, ordered: bool = False) -> ast.List:
    children: list[ast.Node] = [ast.Paragraph(children=[ast.Text(text=text)])]
    if sub is not None:
        children.append(sub)
    return ast.List(ordered=ordered, start=1, items=[ast.ListItem(children=children)])


# ---Схема---


def test_lists_schema_defaults():
    cfg = load_config_from_string("preset: gost-7-32-2017\n")
    assert cfg.lists.mode == "native"
    assert cfg.lists.bullet_nested_format == "{n})"


# ---Native: bullet---


def test_unordered_list_uses_native_numbering(document, config):
    node = _flat_items("Первый", "Второй")
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    # Текст параграфа — только содержимое item-а, маркера в тексте нет.
    assert [p.text for p in paragraphs] == ["Первый", "Второй"]
    pairs = [_numpr(p) for p in paragraphs]
    assert all(pair is not None for pair in pairs)
    assert pairs[0][0] == 0  # ilvl L1
    assert pairs[1] == pairs[0]  # один список — один num

    root = _numbering_root(document)
    assert root is not None
    abstract = _abstract(root, pairs[0][1])
    lvl0 = _lvl(abstract, 0)
    assert _field(lvl0, "w:numFmt") == "bullet"
    assert _field(lvl0, "w:lvlText") == "—"
    # Геометрия уровня: маркер висит в зоне абзацного отступа.
    assert _ind(lvl0) == (_LEFT_TW, _PER_LEVEL_TW)
    assert _field(lvl0, "w:lvlJc") == "left"

    # Прямые ind/tabs на параграфе не дублируем — геометрия из numbering.
    ppr = paragraphs[0]._p.find(qn("w:pPr"))
    assert ppr is not None
    assert ppr.find(qn("w:ind")) is None
    assert ppr.find(qn("w:tabs")) is None


def test_bullet_nested_levels_are_decimal_bracket(document, config):
    """Unordered: L1 «—», L2+ — «1)», «2)» (bullet_nested_format), глубже —
    decimal на большей глубине. Один num на цепочку, ilvl = глубина."""
    inner = _nest("L2", None)
    outer = _nest("L1", inner)
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)

    pairs = [_numpr(p) for p in paragraphs]
    assert pairs[0] is not None and pairs[1] is not None
    assert pairs[0][0] == 0
    assert pairs[1][0] == 1
    assert pairs[1][1] == pairs[0][1]  # вложенность делит num

    root = _numbering_root(document)
    abstract = _abstract(root, pairs[0][1])
    assert _field(_lvl(abstract, 0), "w:numFmt") == "bullet"
    lvl1 = _lvl(abstract, 1)
    assert _field(lvl1, "w:numFmt") == "decimal"
    assert _field(lvl1, "w:lvlText") == "%2)"
    assert _ind(lvl1) == (_LEFT_L2_TW, _PER_LEVEL_TW)
    lvl2 = _lvl(abstract, 2)
    assert _field(lvl2, "w:numFmt") == "decimal"
    assert _field(lvl2, "w:lvlText") == "%3)"


def test_bullet_marker_override_native():
    cfg = load_config_from_string(
        'preset: gost-7-32-2017\noverrides:\n  lists:\n    bullet_marker: "•"\n'
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _flat_items("a"))
    paragraphs = _render_paragraphs(lst, doc)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(doc), pair[1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "•"


def test_bullet_nested_format_override():
    cfg = load_config_from_string(
        'preset: gost-7-32-2017\noverrides:\n  lists:\n    bullet_nested_format: "{n}."\n'
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _nest("L1", _nest("L2", None)))
    paragraphs = _render_paragraphs(lst, doc)
    pair = _numpr(paragraphs[1])
    assert pair is not None
    abstract = _abstract(_numbering_root(doc), pair[1])
    assert _field(_lvl(abstract, 1), "w:lvlText") == "%2."


# ---Native: ordered---


def test_ordered_list_renders_native_arabic(document, config):
    node = _flat_items("Раз", "Два", "Три", ordered=True)
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    assert [p.text for p in paragraphs] == ["Раз", "Два", "Три"]
    pairs = [_numpr(p) for p in paragraphs]
    assert all(pair is not None for pair in pairs)
    assert all(pair[0] == 0 for pair in pairs)
    assert pairs[1][1] == pairs[0][1]

    abstract = _abstract(_numbering_root(document), pairs[0][1])
    lvl0 = _lvl(abstract, 0)
    assert _field(lvl0, "w:numFmt") == "decimal"
    assert _field(lvl0, "w:lvlText") == "%1."


def test_ordered_list_paren_delimiter_native(document, config):
    """``delimiter=')'`` → lvlText ``%1)`` (литеральный delimiter из md)."""
    node = _flat_items("A", "B", "C", ordered=True)
    node.delimiter = ")"
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(document), pair[1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1)"


def test_numbered_format_used_when_no_delimiter():
    """Без delimiter применяется конфиг ``numbered_format``."""
    cfg = load_config_from_string(
        'preset: gost-7-32-2017\noverrides:\n  lists:\n    numbered_format: "{n})"\n'
    )
    doc = build_document(cfg)
    node = _flat_items("a", ordered=True)
    node.delimiter = None
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(doc), pair[1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1)"


def test_md_delimiter_wins_over_numbered_format():
    cfg = load_config_from_string(
        'preset: gost-7-32-2017\noverrides:\n  lists:\n    numbered_format: "{n})"\n'
    )
    doc = build_document(cfg)
    node_dot = _flat_items("a", ordered=True)
    node_dot.delimiter = "."
    lst = List(doc, cfg, node_dot)
    paragraphs = _render_paragraphs(lst, doc)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(doc), pair[1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1."


def test_ordered_list_start_encoded_in_level_start(document, config):
    """``start=5`` корня цепочки → ``w:start val="5"`` на ilvl 0 свежего
    abstractNum. startOverride на w:num не используем: LibreOffice
    применяет его к общему счётчику, и соседние списки продолжались бы."""
    node = _flat_items("a", "b", ordered=True)
    node.start = 5
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    pair = _numpr(paragraphs[0])
    assert pair is not None

    root = _numbering_root(document)
    num = _num_el(root, pair[1])
    assert num.find(qn("w:lvlOverride")) is None
    abstract = _abstract(root, pair[1])
    assert _field(_lvl(abstract, 0), "w:start") == "5"
    assert _field(_lvl(abstract, 1), "w:start") == "1"


def test_ordered_default_start_has_no_override(document, config):
    node = _flat_items("a", ordered=True)
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    root = _numbering_root(document)
    num = _num_el(root, pair[1])
    assert num.find(qn("w:lvlOverride")) is None
    abstract = _abstract(root, pair[1])
    assert _field(_lvl(abstract, 0), "w:start") == "1"


def test_nested_chain_literal_start_uses_startoverride(document, config):
    """``start != 1`` у вложенного узла ПОСЛЕДОВАТЕЛЬНОСТИ (продолжение, не
    корень) — остаётся startOverride на общем num: цепочка делит num."""
    inner = ast.List(
        ordered=True,
        start=5,
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])])],
    )
    outer = _nest("A", inner, ordered=True)
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    pairs = [_numpr(p) for p in paragraphs]
    assert pairs[0][1] == pairs[1][1]
    assert pairs[1][0] == 1

    num = _num_el(_numbering_root(document), pairs[0][1])
    override = num.find(qn("w:lvlOverride"))
    assert override is not None
    assert override.get(qn("w:ilvl")) == "1"
    start = override.find(qn("w:startOverride"))
    assert start is not None
    assert start.get(qn("w:val")) == "5"


def test_nested_ordered_chain_shares_num_and_composes_path(document, config):
    """Ordered-цепочка делит num: ilvl 0/1/2, lvlText ``%1.``, ``%1.%2.``,
    ``%1.%2.%3.`` — иерархические маркеры 1., 1.1., 1.1.1."""
    l3 = _nest("L3", None, ordered=True)
    l2 = _nest("L2", l3, ordered=True)
    l1 = _nest("L1", l2, ordered=True)
    lst = List(document, config, l1)
    paragraphs = _render_paragraphs(lst, document)

    pairs = [_numpr(p) for p in paragraphs]
    assert [pair[0] for pair in pairs] == [0, 1, 2]
    assert pairs[0][1] == pairs[1][1] == pairs[2][1]

    abstract = _abstract(_numbering_root(document), pairs[0][1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1."
    assert _field(_lvl(abstract, 1), "w:lvlText") == "%1.%2."
    assert _field(_lvl(abstract, 2), "w:lvlText") == "%1.%2.%3."
    assert _field(_lvl(abstract, 1), "w:numFmt") == "decimal"


def test_hierarchical_paren_delimiter_composes(document, config):
    """delimiter=')' на цепочке → ``%1)``, ``%1.%2)``, ``%1.%2.%3)``."""
    inner_inner = ast.List(
        ordered=True,
        start=1,
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="deep")])])],
        delimiter=")",
    )
    inner = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="mid")]), inner_inner])
        ],
        delimiter=")",
    )
    outer = ast.List(
        ordered=True,
        start=1,
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="top")]), inner])],
        delimiter=")",
    )
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(document), pair[1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1)"
    assert _field(_lvl(abstract, 1), "w:lvlText") == "%1.%2)"
    assert _field(_lvl(abstract, 2), "w:lvlText") == "%1.%2.%3)"


def test_mixed_ordered_unordered_use_separate_nums(document, config):
    """Bullet под ordered — отдельный num (ilvl 0 своего abstractNum)."""
    bullet_sub = _flat_items("раз", "два")
    outer = _nest("A", bullet_sub, ordered=True)
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)

    pairs = [_numpr(p) for p in paragraphs]
    assert all(pair is not None for pair in pairs)
    assert pairs[0][0] == 0
    assert pairs[1][0] == 0  # bullet-подсписок — свой num с ilvl 0
    assert pairs[1][1] != pairs[0][1]

    root = _numbering_root(document)
    bullet_abstract = _abstract(root, pairs[1][1])
    assert _field(_lvl(bullet_abstract, 0), "w:numFmt") == "bullet"


def test_sibling_lists_restart_numbering(document, config):
    """Два соседних списка — разные numId И разные abstractNum: счётчики
    LibreOffice живут на abstractNum, общий abstractNum продолжал бы
    нумерацию между списками (баг: «1., 2.» потом «3., 4.»)."""
    lst1 = List(document, config, _flat_items("a", ordered=True))
    lst2 = List(document, config, _flat_items("b", ordered=True))
    p1 = _render_paragraphs(lst1, document)
    p2 = _render_paragraphs(lst2, document)

    pair1 = _numpr(p1[0])
    pair2 = _numpr(p2[0])
    assert pair1 is not None and pair2 is not None
    assert pair1[1] != pair2[1]

    root = _numbering_root(document)
    a1 = _abstract(root, pair1[1])
    a2 = _abstract(root, pair2[1])
    assert a1.get(qn("w:abstractNumId")) != a2.get(qn("w:abstractNumId"))


def test_chain_breaks_under_bullet_starts_new_num(document, config):
    """Bullet рвёт arabic-цепочку: внутренний ordered — свежий num, ilvl 0,
    локальный lvlText ``%1.`` (не иерархический)."""
    inner_ordered = ast.List(
        ordered=True,
        start=1,
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="y")])]),
        ],
    )
    bullet = _nest("b", inner_ordered)
    outer = _nest("A", bullet, ordered=True)
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)

    pairs = [_numpr(p) for p in paragraphs]
    assert all(pair is not None for pair in pairs)
    assert pairs[2][1] == pairs[3][1]  # x, y — один num
    assert pairs[2][1] != pairs[0][1]  # не num внешнего ordered
    assert pairs[2][1] != pairs[1][1]  # не num bullet
    assert pairs[2][0] == 0

    abstract = _abstract(_numbering_root(document), pairs[2][1])
    assert _field(_lvl(abstract, 0), "w:lvlText") == "%1."


# ---Native: параграфы item-ов и продолжения---


def test_multi_paragraph_item_renders_continuation_separately(document, config):
    """Head — с numPr; продолжения — без numPr, без маркера в тексте."""
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="Первый абзац item-а")]),
            ast.Paragraph(children=[ast.Text(text="Continuation абзац")]),
        ]
    )
    item2 = ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="Второй item")])])
    node = ast.List(ordered=True, start=1, items=[item, item2])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    assert [p.text for p in paragraphs] == [
        "Первый абзац item-а",
        "Continuation абзац",
        "Второй item",
    ]
    assert _numpr(paragraphs[0]) is not None
    assert _numpr(paragraphs[2]) is not None
    assert _numpr(paragraphs[1]) is None


def test_continuation_alignment_at_text_column(document, config):
    """Продолжение — left_indent на текстовой колонке (уровень 1), first_line 0."""
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="head")]),
            ast.Paragraph(children=[ast.Text(text="cont")]),
        ]
    )
    node = ast.List(ordered=True, start=1, items=[item])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    cont_pf = paragraphs[1].paragraph_format
    assert cont_pf.left_indent is not None
    # Допуск — округление EMU→twips→EMU при записи в docx (до 1 твипа).
    assert abs(int(cont_pf.left_indent) - int(parse_length(config.lists.indent_left))) <= 635
    assert (cont_pf.first_line_indent or 0) == 0


def test_multi_paragraph_with_interleaved_sublist_preserves_order(document, config):
    item = ast.ListItem(
        children=[
            ast.Paragraph(children=[ast.Text(text="head")]),
            _flat_items("sub"),
            ast.Paragraph(children=[ast.Text(text="tail")]),
        ]
    )
    node = ast.List(ordered=True, start=1, items=[item])
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)

    assert [p.text for p in paragraphs] == ["head", "sub", "tail"]


def test_native_item_has_no_marker_runs(document, config):
    """Маркера в runs нет; inline-форматирование содержимого сохраняется."""
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
    assert [r.text for r in runs] == ["жирно"]
    assert runs[0].bold


def test_native_levels_and_geometry_clamp(document, config):
    """5 уровней: ilvl растёт, геометрия зажимается на L4 (L5 == L4)."""
    l5 = _nest("L5", None)
    l4 = _nest("L4", l5)
    l3 = _nest("L3", l4)
    l2 = _nest("L2", l3)
    l1 = _nest("L1", l2)
    lst = List(document, config, l1)
    paragraphs = _render_paragraphs(lst, document)

    pairs = [_numpr(p) for p in paragraphs]
    assert [pair[0] for pair in pairs] == [0, 1, 2, 3, 4]
    assert len({pair[1] for pair in pairs}) == 1

    abstract = _abstract(_numbering_root(document), pairs[0][1])
    lefts = [int(_ind(_lvl(abstract, i))[0]) for i in range(5)]
    assert lefts[0] < lefts[1] < lefts[2] < lefts[3]
    assert lefts[3] == lefts[4] == 709 + 3 * 425


def test_native_geometry_from_config():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\n"
        "overrides:\n"
        "  lists:\n"
        "    indent_left: 1.25cm\n"
        "    indent_per_level: 0.75cm\n"
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _nest("L1", _nest("L2", None)))
    paragraphs = _render_paragraphs(lst, doc)
    pair = _numpr(paragraphs[0])
    assert pair is not None
    abstract = _abstract(_numbering_root(doc), pair[1])
    assert _ind(_lvl(abstract, 0)) == ("709", "425")
    assert _ind(_lvl(abstract, 1)) == ("1134", "425")


def test_native_spacing_zero(document, config):
    node = _flat_items("a")
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    pf = paragraphs[0].paragraph_format
    assert (pf.space_before, pf.space_after) == (0, 0)


def test_list_factory_dispatch(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[_flat_items("a", "b")])
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], List)


# ---Alpha-списки: литеральные маркеры (без изменений поведения)---


def test_alpha_marker_style_renders_russian_letters(document, config):
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


def test_alpha_marker_style_russian_sequence_skips_forbidden_gost_letters(document, config):
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
        'preset: gost-7-32-2017\noverrides:\n  lists:\n    alphabetic_format: "{a}."\n'
    )
    doc = build_document(cfg)
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])])],
    )
    lst = List(doc, cfg, node)
    paragraphs = _render_paragraphs(lst, doc)
    assert paragraphs[0].text.startswith("а.\t")


def test_alpha_list_inline_geometry_and_numid_zero(document, config):
    """Alpha — литеральный маркер, прямая геометрия (ind+tab) и numId=0."""
    node = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="x")])])],
    )
    lst = List(document, config, node)
    paragraphs = _render_paragraphs(lst, document)
    paragraph = paragraphs[0]

    assert paragraph.text == "а)\tx"
    assert _numpr(paragraph) == (0, 0)
    ppr = paragraph._p.find(qn("w:pPr"))
    assert ppr is not None
    ind = ppr.find(qn("w:ind"))
    assert ind is not None
    assert ind.get(qn("w:left")) == _LEFT_TW
    assert ind.get(qn("w:hanging")) == _PER_LEVEL_TW
    tabs = ppr.find(qn("w:tabs"))
    assert tabs is not None
    assert tabs.find(qn("w:tab")).get(qn("w:pos")) == _LEFT_TW


def test_alpha_list_nested_under_arabic(document, config):
    """Alpha-список под native-ordered: маркеры литеральные, отступ глубже."""
    alpha = ast.List(
        ordered=True,
        start=1,
        marker_style="lower-alpha-ru",
        items=[
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="alpha-1")])]),
            ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="alpha-2")])]),
        ],
    )
    outer = _nest("A", alpha, ordered=True)
    outer.items.append(ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="B")])]))
    lst = List(document, config, outer)
    paragraphs = _render_paragraphs(lst, document)

    texts = [p.text for p in paragraphs]
    assert texts[0] == "A"
    assert texts[1].startswith("а)\t")
    assert texts[2].startswith("б)\t")
    assert texts[3] == "B"
    # Внешний уровень — native numPr; alpha — numId 0 и прямой ind глубже.
    assert _numpr(paragraphs[0]) is not None
    assert _numpr(paragraphs[1]) == (0, 0)
    left1 = paragraphs[1].paragraph_format.left_indent
    assert left1 is not None
    assert (
        abs(
            int(left1)
            - int(parse_length(config.lists.indent_left))
            - int(parse_length(config.lists.indent_per_level))
        )
        <= 635
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


# ---Режим inline: литеральные маркеры везде (escape hatch)---


def test_inline_mode_bullet_literal():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\noverrides:\n  lists:\n    mode: inline\n"
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _flat_items("a", "b"))
    paragraphs = _render_paragraphs(lst, doc)

    assert paragraphs[0].text.startswith("—\t")
    assert paragraphs[1].text.startswith("—\t")
    assert _numpr(paragraphs[0]) == (0, 0)
    pf = paragraphs[0].paragraph_format
    assert pf.left_indent is not None
    assert pf.first_line_indent is not None and pf.first_line_indent < 0


def test_inline_mode_ordered_literal():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\noverrides:\n  lists:\n    mode: inline\n"
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _flat_items("a", "b", ordered=True))
    paragraphs = _render_paragraphs(lst, doc)
    assert paragraphs[0].text.startswith("1.\t")
    assert paragraphs[1].text.startswith("2.\t")
    assert _numpr(paragraphs[0]) == (0, 0)


def test_inline_mode_nested_bullets_dash_all_levels():
    """В inline-режиме bullet на всех уровнях — «—» (старое поведение)."""
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\noverrides:\n  lists:\n    mode: inline\n"
    )
    doc = build_document(cfg)
    lst = List(doc, cfg, _nest("L1", _nest("L2", None)))
    paragraphs = _render_paragraphs(lst, doc)
    assert paragraphs[0].text.startswith("—\t")
    assert paragraphs[1].text.startswith("—\t")
    assert _numpr(paragraphs[0]) == (0, 0)


def test_inline_mode_hierarchical_ordered_markers():
    cfg = load_config_from_string(
        "preset: gost-7-32-2017\noverrides:\n  lists:\n    mode: inline\n"
    )
    doc = build_document(cfg)
    l3 = _nest("L3", None, ordered=True)
    l2 = _nest("L2", l3, ordered=True)
    l1 = _nest("L1", l2, ordered=True)
    lst = List(doc, cfg, l1)
    paragraphs = _render_paragraphs(lst, doc)
    texts = [p.text for p in paragraphs]
    assert texts[0].startswith("1.\t")
    assert texts[1].startswith("1.1.  ")
    assert texts[2].startswith("1.1.1.  ")
