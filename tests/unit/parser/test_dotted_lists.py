"""Flat legacy numbering must remain literal Markdown text."""

import pytest

from markdown_gost.core import ast
from markdown_gost.core.parser import parse, walk


@pytest.mark.parametrize("marker", ["1.1.", "1.1.1.", "1.1)", "1.1.1)"])
@pytest.mark.parametrize("prefix", ["", "1. Корень\n    ", "1. Корень\n\n"])
def test_dotted_markers_do_not_create_nested_lists(marker, prefix):
    doc = parse(f"{prefix}{marker} Текст\n")
    lists = [node for node in walk(doc) if isinstance(node, ast.List)]
    assert len(lists) == int(bool(prefix))
    assert any(isinstance(node, ast.Text) and marker in node.text for node in walk(doc))
