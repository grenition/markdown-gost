from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_explicit_pagebreak():
    doc = parse("foo\n\n::: {.page-break}\n:::\n\nbar\n")
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Paragraph", "PageBreak", "Paragraph"]
    assert isinstance(doc.children[1], ast.PageBreak)


def test_pagebreak_does_not_match_template_directive():
    doc = parse('::: {.template name="content"}\n:::\n')
    assert isinstance(doc.children[0], ast.TemplateBlock)
    assert not any(isinstance(c, ast.PageBreak) for c in doc.children)
