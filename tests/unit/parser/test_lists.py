"""CommonMark list boundaries, nesting and explicit marker attributes."""

import pytest

from markdown_gost.core import ast
from markdown_gost.core.parser import parse


@pytest.mark.parametrize(
    "marker,ordered", [("1.", True), ("1)", True), ("-", False), ("+", False), ("*", False)]
)
def test_list_markers(marker, ordered):
    node = parse(f"{marker} Первый\n{marker} Второй\n").children[0]
    assert isinstance(node, ast.List)
    assert node.ordered == ordered
    assert len(node.items) == 2
    if ordered:
        assert node.delimiter == marker[-1]
    assert isinstance(node.items[0].children[0], ast.Paragraph)


@pytest.mark.parametrize(
    "style", ["lower-alpha-ru", "upper-alpha-ru", "lower-alpha-en", "upper-alpha-en", "arabic"]
)
def test_explicit_alphabet_at_top_level_and_in_nested_list(style):
    top = parse(f'1. Один\n2. Два\n{{marker="{style}"}}\n').children[0]
    assert isinstance(top, ast.List) and top.marker_style == style
    doc = parse(f'- Внешний\n  1. Один\n  2. Два\n  {{marker="{style}"}}\n')
    outer = doc.children[0]
    nested = next(node for node in outer.items[0].children if isinstance(node, ast.List))
    assert nested.marker_style == style
    assert len(nested.items) == 2


@pytest.mark.parametrize("text", ["а) Один\nб) Два", "a) One\nB) Two", "ж) Раз\nз) Два"])
def test_bare_alphabetic_markers_remain_text(text):
    assert all(isinstance(node, ast.Paragraph) for node in parse(text).children)


@pytest.mark.parametrize("separator", ["\n", "\n\n"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("delimiter", [".", ")"])
def test_blank_lines_do_not_restart_ordered_lists(separator, newline, delimiter):
    text = f"1{delimiter} A\n2{delimiter} B\n{separator}1{delimiter} C\n2{delimiter} D"
    nodes = parse(text.replace("\n", newline)).children
    assert len(nodes) == 1
    assert isinstance(nodes[0], ast.List) and len(nodes[0].items) == 4


@pytest.mark.parametrize("separator", ["Параграф", "<!-- separate -->", "```text\ncode\n```"])
def test_content_between_lists_restarts_numbering(separator):
    doc = parse(f"1. A\n2. B\n\n{separator}\n\n1. C\n2. D\n")
    lists = [node for node in doc.children if isinstance(node, ast.List)]
    assert len(lists) == 2
    assert all(node.start == 1 and len(node.items) == 2 for node in lists)


def test_start_number_and_multiple_paragraph_items():
    node = parse("5. Пятый\n\n   Продолжение\n\n6. Шестой\n").children[0]
    assert isinstance(node, ast.List) and node.start == 5
    assert len(node.items) == 2
    assert len(node.items[0].children) == 2


@pytest.mark.parametrize("delimiter", [".", ")"])
def test_nested_numbering_uses_indentation(delimiter):
    node = parse(
        f"1{delimiter} Корень\n   1{delimiter} Второй\n"
        f"      1{delimiter} Третий\n2{delimiter} Корень\n"
    ).children[0]
    assert isinstance(node, ast.List) and len(node.items) == 2
    nested = next(child for child in node.items[0].children if isinstance(child, ast.List))
    deep = next(child for child in nested.items[0].children if isinstance(child, ast.List))
    assert node.delimiter == nested.delimiter == deep.delimiter == delimiter
