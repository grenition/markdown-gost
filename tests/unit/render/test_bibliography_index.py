from __future__ import annotations

import pytest

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex


def _config(yaml: str = "preset: default\n"):
    return load_config_from_string(yaml)


def _source(source_id: str, **fields: object) -> ast.BibliographySource:
    return ast.BibliographySource(id=source_id, fields=dict(fields))


def test_citation_order_reuses_numbers_for_repeated_sources() -> None:
    doc = ast.Document(
        children=[
            ast.Paragraph(
                children=[
                    ast.Citation(key="b"),
                    ast.Text(text=", "),
                    ast.Citation(key="a"),
                    ast.Text(text=", "),
                    ast.Citation(key="b"),
                ]
            ),
            ast.Bibliography(sources=[_source("a", title="A"), _source("b", title="B")]),
        ]
    )

    index = BibliographyIndex.from_document(doc, _config())

    assert index.number_for("b") == 1
    assert index.number_for("a") == 2
    assert [entry.source.id for entry in index.entries()] == ["b", "a"]


def test_citation_order_omits_uncited_sources() -> None:
    doc = ast.Document(
        children=[
            ast.Paragraph(children=[ast.Citation(key="used")]),
            ast.Bibliography(
                sources=[
                    _source("unused", title="Unused"),
                    _source("used", title="Used"),
                ]
            ),
        ]
    )

    index = BibliographyIndex.from_document(doc, _config())

    assert [entry.source.id for entry in index.entries()] == ["used"]


def test_duplicate_source_ids_raise() -> None:
    doc = ast.Document(
        children=[
            ast.Bibliography(sources=[_source("dup", title="A"), _source("dup", title="B")])
        ]
    )

    with pytest.raises(ValueError, match="duplicate bibliography source id.*dup"):
        BibliographyIndex.from_document(doc, _config())


def test_missing_source_raises() -> None:
    doc = ast.Document(children=[ast.Paragraph(children=[ast.Citation(key="missing")])])

    with pytest.raises(ValueError, match="missing bibliography source.*missing"):
        BibliographyIndex.from_document(doc, _config())


def test_input_order_can_be_selected() -> None:
    cfg = _config("preset: default\noverrides:\n  bibliography:\n    order: input\n")
    doc = ast.Document(
        children=[
            ast.Paragraph(children=[ast.Citation(key="b"), ast.Citation(key="a")]),
            ast.Bibliography(sources=[_source("a", title="A"), _source("b", title="B")]),
        ]
    )

    index = BibliographyIndex.from_document(doc, cfg)

    assert [entry.source.id for entry in index.entries()] == ["a", "b"]
    assert index.number_for("a") == 1
    assert index.number_for("b") == 2


def test_minimal_gost_uses_raw_text_when_present() -> None:
    doc = ast.Document(
        children=[ast.Bibliography(sources=[_source("raw", text="ГОСТ. Описание.")])]
    )
    index = BibliographyIndex.from_document(doc, _config())

    assert index.format_entry("raw") == "ГОСТ. Описание."


def test_minimal_gost_builds_string_from_known_fields() -> None:
    doc = ast.Document(
        children=[
            ast.Bibliography(
                sources=[
                    _source(
                        "book",
                        authors=["Иванов И.И.", "Петров П.П."],
                        title="Основы",
                        city="М.",
                        publisher="Наука",
                        year=2020,
                        url="https://example.test",
                    )
                ]
            )
        ]
    )

    index = BibliographyIndex.from_document(doc, _config())

    assert index.format_entry("book") == (
        "Иванов И.И., Петров П.П. Основы. М.: Наука, 2020. URL: https://example.test"
    )
