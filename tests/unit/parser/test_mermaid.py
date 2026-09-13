from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_mermaid_block():
    src = "```mermaid\nflowchart LR\n  A --> B\n```\n"
    doc = parse(src)
    node = doc.children[0]
    assert isinstance(node, ast.Mermaid)
    assert "flowchart LR" in node.code
    assert "A --> B" in node.code


def test_diagram_caption_before_mermaid():
    src = "```mermaid\ngraph A\n```\n\n: Процессы\n"
    doc = parse(src)
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Caption", "Mermaid"]
    assert doc.children[0].target == "diagram"
    assert doc.children[0].text == "Процессы"
