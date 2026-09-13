"""Юнит-тесты реестра шаблонов (T022)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from markdown_gost import templates as tpl_pkg
from markdown_gost.config.loader import load_config_from_string
from markdown_gost.render.document_factory import build_document
from markdown_gost.renderable.base import Renderable
from markdown_gost.renderable.paragraph import Paragraph
from markdown_gost.templates import (
    TemplateContext,
    list_templates,
    register,
    render_template,
    schema_from_yaml,
    unregister,
)


class _Params(BaseModel):
    title: str


def _stub_render(params: dict[str, Any], parent: TemplateContext) -> Renderable:
    p = Paragraph(parent.document, parent.config)
    from markdown_gost.core.ast import nodes as ast

    p.add_inline_nodes([ast.Text(text=params["title"])])
    return p


@pytest.fixture
def context():
    config = load_config_from_string("preset: default\n")
    document = build_document(config)
    return TemplateContext(document=document, config=config)


@pytest.fixture(autouse=True)
def _isolate_registry():
    snapshot = list(list_templates())
    yield
    for name in list(list_templates()):
        if name not in snapshot:
            unregister(name)


def test_register_and_list():
    assert "demo" not in list_templates()
    register("demo", _stub_render, _Params)
    assert "demo" in list_templates()


def test_register_rejects_empty_name():
    with pytest.raises(ValueError):
        register("", _stub_render, _Params)


def test_register_overwrites_same_name():
    register("demo", _stub_render, _Params)
    register("demo", _stub_render, _Params)  # same name → no error
    assert list_templates().count("demo") == 1


def test_render_template_validates_params(context):
    register("demo", _stub_render, _Params)
    out = render_template("demo", {"title": "Hello"}, context)
    assert isinstance(out, Paragraph)
    assert out.docx_paragraph.text == "Hello"


def test_render_template_invalid_params_returns_placeholder(context):
    register("demo", _stub_render, _Params)
    # отсутствует обязательное поле title
    out = render_template("demo", {}, context)
    assert isinstance(out, Paragraph)
    assert "demo" in out.docx_paragraph.text.lower()


def test_render_unknown_template_returns_placeholder(context):
    out = render_template("ghost-template", {}, context)
    assert isinstance(out, Paragraph)
    text = out.docx_paragraph.text.lower()
    assert "ghost-template" in text


def test_unregister(context):
    register("demo", _stub_render, _Params)
    unregister("demo")
    assert "demo" not in list_templates()


def test_schema_from_yaml(tmp_path: Path):
    schema_yaml = tmp_path / "schema.yaml"
    schema_yaml.write_text(
        """
fields:
  title:
    type: str
    required: true
  authors:
    type: list[str]
    default: []
  year:
    type: int
    default: null
""",
        encoding="utf-8",
    )
    schema_cls = schema_from_yaml(schema_yaml)
    assert issubclass(schema_cls, BaseModel)
    inst = schema_cls.model_validate({"title": "T"})
    assert inst.title == "T"
    assert inst.authors == []
    assert inst.year is None


def test_schema_from_yaml_required_field_missing(tmp_path: Path):
    schema_yaml = tmp_path / "schema.yaml"
    schema_yaml.write_text(
        "fields:\n  title:\n    type: str\n    required: true\n",
        encoding="utf-8",
    )
    schema_cls = schema_from_yaml(schema_yaml)
    with pytest.raises(ValidationError):
        schema_cls.model_validate({})


def test_schema_from_yaml_extra_fields_forbidden(tmp_path: Path):
    schema_yaml = tmp_path / "schema.yaml"
    schema_yaml.write_text(
        "fields:\n  title:\n    type: str\n    required: true\n",
        encoding="utf-8",
    )
    schema_cls = schema_from_yaml(schema_yaml)
    with pytest.raises(ValidationError):
        schema_cls.model_validate({"title": "T", "extra": "nope"})


def test_lazy_render_fn_resolution(context, monkeypatch):
    """`register` принимает строку 'pkg.module:attr' для отложенной загрузки."""
    import sys
    import types

    mod = types.ModuleType("md2gost_test_lazy_tpl")

    def render(params: dict[str, Any], parent: TemplateContext) -> Paragraph:
        from markdown_gost.core.ast import nodes as ast

        p = Paragraph(parent.document, parent.config)
        p.add_inline_nodes([ast.Text(text=params["title"])])
        return p

    mod.render = render  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "md2gost_test_lazy_tpl", mod)

    register("demo", "md2gost_test_lazy_tpl:render", _Params)
    out = render_template("demo", {"title": "Hi"}, context)
    assert isinstance(out, Paragraph)
    assert out.docx_paragraph.text == "Hi"


def test_render_fn_not_leaked_via_public_api():
    """Публичный API не возвращает render_fn — он деталь реализации."""
    register("demo", _stub_render, _Params)
    public_names = {n for n in dir(tpl_pkg) if not n.startswith("_")}
    # в публичном API не должно быть способа достать render_fn
    assert "get_render_fn" not in public_names
