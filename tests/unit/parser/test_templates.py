from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_short_template_block():
    doc = parse('Перед.\n\n::: {.template name="content"}\n:::\n\nПосле.\n')
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Paragraph", "TemplateBlock", "Paragraph"]
    tpl = doc.children[1]
    assert isinstance(tpl, ast.TemplateBlock)
    assert tpl.name == "content"
    assert tpl.params == {}


def test_long_template_block_with_yaml():
    src = (
        '::: {.template name="titlepage-mirea"}\n'
        "title: Отчёт\n"
        "year: 2026\n"
        "authors:\n"
        "  - Иванов\n"
        "  - Петров\n"
        ":::\n"
        "\n"
        "После шаблона.\n"
    )
    doc = parse(src)
    tpl = doc.children[0]
    assert isinstance(tpl, ast.TemplateBlock)
    assert tpl.name == "titlepage-mirea"
    assert tpl.params["title"] == "Отчёт"
    assert tpl.params["year"] == 2026
    assert tpl.params["authors"] == ["Иванов", "Петров"]


def test_short_template_at_start_of_doc():
    doc = parse('::: {.template name="content"}\n:::\n\nПосле.\n')
    tpl = doc.children[0]
    assert isinstance(tpl, ast.TemplateBlock)
    assert tpl.name == "content"
    assert tpl.params == {}


def test_template_does_not_swallow_pagebreak_after():
    doc = parse('::: {.template name="content"}\n:::\n\n::: {.page-break}\n:::\n\nПосле.\n')
    types = [type(c).__name__ for c in doc.children]
    assert "TemplateBlock" in types
    assert "PageBreak" in types
