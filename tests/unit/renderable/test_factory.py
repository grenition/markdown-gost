"""Юнит-тесты RenderableFactory: AST → renderables."""

from __future__ import annotations

import pytest

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.bibliography import Bibliography
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.heading import Heading
from markdown_gost.renderable.page_break import PageBreak
from markdown_gost.renderable.paragraph import Paragraph


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture
def document(config):
    return build_document(config)


def test_factory_dispatches_paragraph(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[ast.Paragraph(children=[ast.Text(text="hi")])])
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Paragraph)
    assert not isinstance(rendered[0], Heading)


def test_factory_dispatches_heading(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(
        children=[ast.Heading(level=1, numbered=True, children=[ast.Text(text="Глава")])]
    )
    rendered = f.create_all(doc_ast)
    assert isinstance(rendered[0], Heading)
    assert rendered[0].level == 1


def test_factory_dispatches_page_break(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[ast.PageBreak()])
    rendered = f.create_all(doc_ast)
    assert isinstance(rendered[0], PageBreak)


def test_factory_dispatches_equation(document, config):
    """``ast.Equation`` теперь — собственный Equation-renderable (T015)."""
    from markdown_gost.renderable.equation import Equation

    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[ast.Equation(latex="x^2")])
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Equation)


def test_factory_unsupported_node_emits_stub_paragraph(document, config):
    f = RenderableFactory(document, config, Numberer())
    # ast.Mermaid ещё не поддерживается рендером — должна вернуться
    # stub-плашка с указанием типа. ast.Listing/ast.Equation теперь имеют
    # собственный renderable (T014/T015), для stub-проверки используем
    # Mermaid (ждёт T024).
    doc_ast = ast.Document(children=[ast.Mermaid(code="graph TD; a-->b")])
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Paragraph)
    assert "not supported" in rendered[0].docx_paragraph.text.lower()


def test_factory_builds_bibliography_index_before_paragraphs(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(
        children=[
            ast.Paragraph(children=[ast.Text(text="См. "), ast.Citation(key="src")]),
            ast.Bibliography(
                sources=[ast.BibliographySource(id="src", fields={"title": "Источник"})]
            ),
        ]
    )

    rendered = f.create_all(doc_ast)

    assert isinstance(rendered[0], Paragraph)
    assert rendered[0].docx_paragraph.text == "См. [1]"
    assert isinstance(rendered[1], Bibliography)


def test_factory_missing_citation_source_fails_early(document, config):
    f = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(children=[ast.Paragraph(children=[ast.Citation(key="missing")])])

    with pytest.raises(ValueError, match="missing bibliography source.*missing"):
        f.create_all(doc_ast)
