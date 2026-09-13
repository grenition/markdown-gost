from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_block_equation():
    src = "$$\ne^{i\\pi} + 1 = 0\n$$\n"
    doc = parse(src)
    eq = doc.children[0]
    assert isinstance(eq, ast.Equation)
    assert eq.latex.strip() == "e^{i\\pi} + 1 = 0"


def test_block_equation_inline_form():
    doc = parse("$$ x + y $$\n")
    eq = doc.children[0]
    assert isinstance(eq, ast.Equation)
    assert eq.latex == "x + y"


def test_inline_equation_in_paragraph():
    doc = parse("Уравнение Эйлера: $e^{i\\pi}+1=0$ — красиво.\n")
    p = doc.children[0]
    types = [type(c).__name__ for c in p.children]
    assert "InlineEquation" in types
    eq = next(c for c in p.children if isinstance(c, ast.InlineEquation))
    assert eq.latex == "e^{i\\pi}+1=0"


def test_inline_equation_does_not_eat_block():
    doc = parse("text\n\n$$\na=b\n$$\n\nmore\n")
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Paragraph", "Equation", "Paragraph"]
