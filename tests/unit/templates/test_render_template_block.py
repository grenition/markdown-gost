"""Полный цикл: AST TemplateBlock → RenderableFactory → Renderable из реестра."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.paragraph import Paragraph
from markdown_gost.templates import (
    TemplateContext,
    list_templates,
    register,
    unregister,
)


class _Params(BaseModel):
    title: str


def _render(params: dict[str, Any], parent: TemplateContext) -> Paragraph:
    p = Paragraph(parent.document, parent.config)
    p.add_inline_nodes([ast.Text(text=f"TPL:{params['title']}")])
    return p


@pytest.fixture
def config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture
def document(config):
    return build_document(config)


@pytest.fixture(autouse=True)
def _isolate_registry():
    snapshot = list(list_templates())
    yield
    for name in list(list_templates()):
        if name not in snapshot:
            unregister(name)


def test_factory_dispatches_template_block_to_registry(document, config):
    register("hello", _render, _Params)
    factory = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(
        children=[ast.TemplateBlock(name="hello", params={"title": "World"})]
    )
    rendered = factory.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Paragraph)
    assert rendered[0].docx_paragraph.text == "TPL:World"


def test_factory_template_block_unknown_emits_placeholder(document, config):
    factory = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(
        children=[ast.TemplateBlock(name="missing-tpl", params={})]
    )
    rendered = factory.create_all(doc_ast)
    assert len(rendered) == 1
    text = rendered[0].docx_paragraph.text.lower()
    assert "missing-tpl" in text


def test_factory_template_block_invalid_params_emits_placeholder(document, config):
    register("hello", _render, _Params)
    factory = RenderableFactory(document, config, Numberer())
    doc_ast = ast.Document(
        children=[ast.TemplateBlock(name="hello", params={"wrong": "x"})]
    )
    rendered = factory.create_all(doc_ast)
    assert len(rendered) == 1
    text = rendered[0].docx_paragraph.text.lower()
    assert "hello" in text
