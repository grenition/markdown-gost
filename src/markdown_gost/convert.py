"""Public conversion pipeline.

Связка: markdown → AST → docx → (pdf).
"""

from __future__ import annotations

import io
from typing import Literal

from docx.document import Document as DocxDocument

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.core.parser import parse
from markdown_gost.output.pdf_writer import convert_to_pdf
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.render_index import RenderIndex
from markdown_gost.render.renderer import Renderer
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.storage.base import Storage
from markdown_gost.storage.fs import FilesystemStorage

Format = Literal["docx", "pdf"]


def _docx_to_bytes(document: DocxDocument) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _render_docx_with_index(
    ast_doc: ast.Document, config: Config, storage: Storage
) -> tuple[DocxDocument, RenderIndex]:
    document = build_document(config)
    numberer = Numberer()
    factory = RenderableFactory(document, config, numberer, storage=storage)
    renderables = factory.create_all(ast_doc)
    renderer = Renderer(document)
    renderer.process(renderables)
    return document, renderer.index


def convert(
    markdown: str,
    config: Config,
    format: Format = "docx",
    *,
    storage: Storage | None = None,
) -> bytes:
    ast_doc = parse(markdown)
    effective_storage = storage if storage is not None else FilesystemStorage()

    if format == "docx":
        document, _ = _render_docx_with_index(ast_doc, config, effective_storage)
        return _docx_to_bytes(document)
    if format == "pdf":
        document, _ = _render_docx_with_index(ast_doc, config, effective_storage)
        return convert_to_pdf(_docx_to_bytes(document))
    raise ValueError(f"Unknown format: {format!r}")


def render_pdf_with_index(
    markdown: str,
    config: Config,
    *,
    storage: Storage | None = None,
) -> tuple[bytes, RenderIndex]:
    """Конвертировать markdown в PDF, попутно вернув RenderIndex.

    Используется ``/api/preview`` (T030), где фронту нужны метаданные
    ``X-Total-Pages`` и ``X-Heading-Anchors`` поверх PDF-тела. Логика рендера
    та же, что у ``convert(..., format='pdf')`` — единый источник правды.
    """

    ast_doc = parse(markdown)
    effective_storage = storage if storage is not None else FilesystemStorage()
    document, render_index = _render_docx_with_index(
        ast_doc, config, effective_storage
    )
    pdf_bytes = convert_to_pdf(_docx_to_bytes(document))
    return pdf_bytes, render_index
