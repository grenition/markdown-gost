from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_basic_table():
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    doc = parse(src)
    table = doc.children[0]
    assert isinstance(table, ast.Table)
    assert len(table.rows) == 3
    assert table.rows[0].header is True
    assert all(c.header for c in table.rows[0].cells)
    assert table.rows[1].header is False
    assert len(table.rows[0].cells) == 2


def test_table_with_caption():
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n\n: Список продуктов\n"
    doc = parse(src)
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Caption", "Table"]
    cap = doc.children[0]
    assert isinstance(cap, ast.Caption)
    assert cap.target == "table"
    assert cap.text == "Список продуктов"


def test_table_alignment():
    src = "| A | B | C |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n"
    doc = parse(src)
    table = doc.children[0]
    aligns = [c.align for c in table.rows[0].cells]
    assert aligns == ["left", "center", "right"]


def test_table_caption_with_widths_attrs():
    src = (
        "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n"
        '\n: Список продуктов {widths="20%, 30%, 50%"}\n'
    )
    doc = parse(src)
    cap = doc.children[0]
    assert isinstance(cap, ast.Caption)
    assert cap.target == "table"
    assert cap.text == "Список продуктов"
    assert cap.attrs == {"widths": "20%, 30%, 50%"}


def test_table_caption_widths_and_heights():
    src = (
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
        '\n: Caption {widths="6cm, auto" heights="auto, 1cm, auto"}\n'
    )
    doc = parse(src)
    cap = doc.children[0]
    assert isinstance(cap, ast.Caption)
    assert cap.attrs == {
        "widths": "6cm, auto",
        "heights": "auto, 1cm, auto",
    }


def test_table_caption_no_attrs_keeps_empty_dict():
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n\n: Без атрибутов\n"
    doc = parse(src)
    cap = doc.children[0]
    assert isinstance(cap, ast.Caption)
    assert cap.text == "Без атрибутов"
    assert cap.attrs == {}
