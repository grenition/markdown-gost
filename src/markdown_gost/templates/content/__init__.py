"""Шаблон ``content`` — оглавление документа (T023)."""

from __future__ import annotations

from pathlib import Path

from markdown_gost.templates import register, schema_from_yaml

from .preview import render_preview
from .render import render

_HERE = Path(__file__).parent

register(
    "content",
    render,
    schema_from_yaml(_HERE / "schema.yaml"),
    preview_fn=render_preview,
)
