from __future__ import annotations

import pytest

from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_cite_reference_becomes_citation() -> None:
    doc = parse("Текст со ссылкой [@ivanov2020].\n")
    paragraph = doc.children[0]

    assert isinstance(paragraph, ast.Paragraph)
    citations = [child for child in paragraph.children if isinstance(child, ast.Citation)]
    assert len(citations) == 1
    assert citations[0].key == "ivanov2020"


def test_non_cite_reference_is_unchanged() -> None:
    doc = parse("См. [](#products).\n")
    paragraph = doc.children[0]

    assert isinstance(paragraph, ast.Paragraph)
    refs = [child for child in paragraph.children if isinstance(child, ast.Reference)]
    assert len(refs) == 1
    assert refs[0].type == ""
    assert refs[0].name == "products"


def test_fenced_bibliography_yaml_list() -> None:
    doc = parse(
        "::: {.bibliography}\n"
        "- id: ivanov2020\n"
        "  type: book\n"
        "  authors:\n"
        "    - Иванов И.И.\n"
        "  title: Основы\n"
        "  year: 2020\n"
        "- id: site\n"
        "  text: ГОСТ Р 7.0.100-2018. Библиографическая запись.\n"
        ":::\n"
    )

    bibliography = doc.children[0]
    assert isinstance(bibliography, ast.Bibliography)
    assert [source.id for source in bibliography.sources] == ["ivanov2020", "site"]
    assert bibliography.sources[0].type == "book"
    assert bibliography.sources[0].fields["title"] == "Основы"
    assert (
        bibliography.sources[1].fields["text"] == "ГОСТ Р 7.0.100-2018. Библиографическая запись."
    )


def test_fenced_bibliography_accepts_quoted_url_text() -> None:
    doc = parse(
        "::: {.bibliography}\n"
        "- id: site\n"
        '  text: "Документация проекта. URL: https://example.test"\n'
        ":::\n"
    )

    bibliography = doc.children[0]

    assert isinstance(bibliography, ast.Bibliography)
    assert (
        bibliography.sources[0].fields["text"] == "Документация проекта. URL: https://example.test"
    )


def test_invalid_bibliography_yaml_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="bibliography YAML"):
        parse("::: {.bibliography}\n- id: ok\n  title: [broken\n:::\n")


def test_bibliography_source_without_id_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="bibliography source.*id"):
        parse("::: {.bibliography}\n- title: Missing id\n:::\n")
