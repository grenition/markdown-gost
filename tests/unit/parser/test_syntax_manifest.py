"""Acceptance contract for skills/markdown-gost/syntax.md (no legacy syntax)."""

import pytest

from markdown_gost.core import ast
from markdown_gost.core.parser import parse, walk


def test_attributes_captions_and_appendix_scope():
    doc = parse(
        "# *Введение* {.unnumbered #intro}\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        ': Данные {#data widths="40%, 60%"}\n\n'
        "# Материалы {.appendix #materials}\n\n"
        "## Набор\n\n# Итоги\n"
    )
    heading, caption, table, appendix, subheading, end, final = doc.children
    assert isinstance(heading, ast.Heading)
    assert not heading.numbered
    assert heading.identifier == "intro"
    assert isinstance(heading.children[0], ast.Emphasis)
    assert isinstance(caption, ast.Caption) and caption.target == "table"
    assert caption.text == "Данные"
    assert caption.attrs == {"widths": "40%, 60%"}
    assert isinstance(table, ast.Table) and table.identifier == "data"
    assert isinstance(appendix, ast.AppendixStart)
    assert appendix.identifier == "materials"
    assert isinstance(subheading, ast.Heading) and subheading.level == 1
    assert isinstance(end, ast.AppendixEnd)
    assert isinstance(final, ast.Heading) and final.level == 1


def test_attributes_do_not_leak_from_code_into_images():
    code = "![Fake](fake.png){width=1cm}\n%table literal\n---content\n"
    doc = parse(f"```text\n{code}```\n\n![Real](real.png){{#real width=8cm height=auto}}\n")
    listing, paragraph = doc.children
    assert isinstance(listing, ast.Listing) and listing.code == code
    assert isinstance(paragraph, ast.Paragraph)
    image = paragraph.children[0]
    assert isinstance(image, ast.Image) and image.identifier == "real"
    assert image.width == ast.Length(value=8, unit="cm")
    assert image.height == ast.Length(value=0, unit="auto")


def test_container_parameters_and_bibliography():
    doc = parse(
        '::: {.template name="content" depth=3 dot_leader=false}\n:::\n\n'
        '::: {.template name="titlepage-university"}\n'
        "title: Работа\nauthors:\n  - label: Студент\n    names: [Иванов]\n:::\n\n"
        "Текст [@book].\n\n::: {.bibliography}\n"
        "- id: book\n  text: Учебник\n:::\n"
    )
    toc, title, paragraph, sources = doc.children
    assert isinstance(toc, ast.TemplateBlock)
    assert toc.params == {"depth": 3, "dot_leader": False}
    assert isinstance(title, ast.TemplateBlock)
    assert title.params["authors"][0]["names"] == ["Иванов"]
    assert isinstance(paragraph, ast.Paragraph)
    assert any(isinstance(n, ast.Citation) and n.key == "book" for n in paragraph.children)
    assert isinstance(sources, ast.Bibliography)


def test_links_spans_and_numbered_list_attributes():
    doc = parse(
        "[**Важно** и `код`]{.underline}; [](#data); [таблица](#data).\n\n"
        '1. Один\n2. Два\n{marker="lower-alpha-ru"}\n'
    )
    paragraph, items = doc.children
    assert isinstance(paragraph, ast.Paragraph)
    assert isinstance(paragraph.children[0], ast.Underline)
    assert any(isinstance(n, ast.Reference) and n.name == "data" for n in paragraph.children)
    assert any(isinstance(n, ast.Link) and n.url == "#data" for n in paragraph.children)
    assert isinstance(items, ast.List) and items.marker_style == "lower-alpha-ru"


def test_markdown_semantics_and_legacy_are_not_reinterpreted():
    doc = parse(
        "# *Обычный курсив*\n\n---\n\n"
        "%table literal\n\n%appendix literal\n\n---content\n\n"
        "++literal++ @cite:book @table:data\n\n"
        "```bibliography\n- id: book\n```\n\n"
        "1. First\n\n1. Second\n"
    )
    assert isinstance(doc.children[0], ast.Heading) and doc.children[0].numbered
    assert isinstance(doc.children[1], ast.ThematicBreak)
    assert not any(
        isinstance(
            n,
            ast.Caption | ast.AppendixStart | ast.TemplateBlock | ast.Bibliography | ast.PageBreak,
        )
        for n in doc.children
    )
    items = doc.children[-1]
    assert isinstance(items, ast.List) and len(items.items) == 2


@pytest.mark.parametrize(
    "text",
    [
        ": Orphan\n",
        "Text\n{width=8cm}\n",
        "![Image](a.png){width=wrong}\n",
        "# Heading {.unknown}\n",
        "# Heading {#one #two}\n",
        "# One {#same}\n\n# Two {#same}\n",
        '::: {.template name="content"}\n',
        "::: {.page-break}\nUnexpected body\n:::\n",
        '::: {.template name="content" depth=3}\ndepth: 2\n:::\n',
        "## Appendix {.appendix}\n",
    ],
)
def test_invalid_extensions_fail_explicitly(text):
    with pytest.raises(ValueError):
        parse(text)


def test_extensions_inside_code_and_escaped_text_stay_literal():
    doc = parse(
        "`[@book] [word]{.underline} ![](a.png){width=2cm}`\n\n"
        "\\[@book] and \\{#id}\n\n"
        "\\: Not a caption\n\n"
        "    ::: {.page-break}\n    :::\n"
    )
    assert not any(
        isinstance(node, ast.Citation | ast.Underline | ast.Image | ast.PageBreak)
        for node in walk(doc)
    )


def test_reference_style_images_and_balanced_paths_keep_attributes():
    doc = parse("![Caption][image]{#picture width=2cm}\n\n[image]: <folder/a(b).png>\n")
    image = next(node for node in walk(doc) if isinstance(node, ast.Image))
    assert image.src == "folder/a(b).png"
    assert image.identifier == "picture"
    assert image.width == ast.Length(value=2, unit="cm")


def test_nested_group_preserves_fenced_code_containing_container_markers():
    doc = parse(":::: {.group}\n::: {.group}\n```text\n::::\n::: {.page-break}\n```\n:::\n::::\n")
    assert len(doc.children) == 1
    assert isinstance(doc.children[0], ast.Listing)
    assert doc.children[0].code == "::::\n::: {.page-break}\n"
