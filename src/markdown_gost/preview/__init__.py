"""Internal preview layout model.

This package builds a lightweight page/block model from markdown without
touching the DOCX/PDF/LibreOffice pipeline.
"""

from markdown_gost.preview.builder import build_preview_model
from markdown_gost.preview.html import render_preview_html, render_preview_stylesheet
from markdown_gost.preview.model import (
    PreviewAnchor,
    PreviewBlock,
    PreviewDocument,
    PreviewImageDimension,
    PreviewInline,
    PreviewLength,
    PreviewMargins,
    PreviewPage,
    PreviewPageGeometry,
)

__all__ = [
    "PreviewAnchor",
    "PreviewBlock",
    "PreviewDocument",
    "PreviewImageDimension",
    "PreviewInline",
    "PreviewLength",
    "PreviewMargins",
    "PreviewPage",
    "PreviewPageGeometry",
    "build_preview_model",
    "render_preview_html",
    "render_preview_stylesheet",
]
