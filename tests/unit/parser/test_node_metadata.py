from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def _walk(node):
    yield node
    for attr in ("children", "items", "rows", "cells"):
        for child in getattr(node, attr, []) or []:
            if isinstance(child, ast.Node):
                yield from _walk(child)


def test_every_node_has_unique_id():
    doc = parse("# Заголовок\n\nПараграф.\n\n- a\n- b\n\n```py\nx=1\n```\n\n$$\nx\n$$\n")
    ids = [n.node_id for n in _walk(doc)]
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, str) and len(i) > 0 for i in ids)


def test_every_node_has_source_position_attribute():
    doc = parse("# H\n\np\n")
    for n in _walk(doc):
        assert hasattr(n, "source_position")


def test_parse_returns_document():
    doc = parse("hi\n")
    assert isinstance(doc, ast.Document)


def test_parse_is_stable_for_equal_input():
    a = parse("# A\n\nb\n")
    b = parse("# A\n\nb\n")
    # Структуры одинаковые (типы, поля кроме node_id).
    assert _shape(a) == _shape(b)


def _shape(node):
    if isinstance(node, ast.Text):
        return ("Text", node.text)
    if isinstance(node, ast.InlineCode):
        return ("InlineCode", node.code)
    if isinstance(node, ast.LineBreak):
        return ("LineBreak", node.soft)
    if isinstance(node, ast.InlineEquation):
        return ("InlineEquation", node.latex)
    if isinstance(node, ast.Reference):
        return ("Reference", node.type, node.name)
    if isinstance(node, ast.Heading):
        return ("Heading", node.level, node.numbered, [_shape(c) for c in node.children])
    if isinstance(node, ast.Paragraph):
        return ("Paragraph", [_shape(c) for c in node.children])
    if isinstance(node, ast.Strong):
        return ("Strong", [_shape(c) for c in node.children])
    if isinstance(node, ast.Emphasis):
        return ("Emphasis", [_shape(c) for c in node.children])
    if isinstance(node, ast.Link):
        return ("Link", node.url, [_shape(c) for c in node.children])
    if isinstance(node, ast.Image):
        return ("Image", node.src, node.unique_name, node.width, node.height)
    if isinstance(node, ast.Caption):
        return ("Caption", node.target, node.text)
    if isinstance(node, ast.Listing):
        return ("Listing", node.language, node.code)
    if isinstance(node, ast.Equation):
        return ("Equation", node.latex)
    if isinstance(node, ast.Mermaid):
        return ("Mermaid", node.code)
    if isinstance(node, ast.PageBreak):
        return ("PageBreak",)
    if isinstance(node, ast.TemplateBlock):
        return ("TemplateBlock", node.name, node.params)
    if isinstance(node, ast.List):
        return ("List", node.ordered, node.start, [_shape(i) for i in node.items])
    if isinstance(node, ast.ListItem):
        return ("ListItem", [_shape(c) for c in node.children])
    if isinstance(node, ast.Table):
        return ("Table", [_shape(r) for r in node.rows])
    if isinstance(node, ast.TableRow):
        return ("Row", node.header, [_shape(c) for c in node.cells])
    if isinstance(node, ast.TableCell):
        return ("Cell", node.align, node.header, [_shape(c) for c in node.children])
    if isinstance(node, ast.Document):
        return ("Document", [_shape(c) for c in node.children])
    return (type(node).__name__,)
