"""Postprocessor pipeline for the import flow (T033, T035).

Composes line-based transformers in fixed order. See the package-level
:file:`README.md` for the rationale behind the line-based representation and
the per-stage error policy.

``listing_wrapper`` (T035) is conditional on a monospace-paragraph scan
having been performed before pandoc — the pipeline injects it just before
``caption_folder`` so freshly wrapped fenced blocks can pick up an adjacent
``Листинг N — Caption`` and turn it into a trailing ``: Caption``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..listing_detector import ParagraphRange
from . import (
    caption_folder,
    heading_normalizer,
    html_table_converter,
    inline_normalizer,
    listing_wrapper,
    unnumbered_heading_detector,
)


def postprocess(
    markdown: str,
    monospace_ranges: Sequence[ParagraphRange] | None = None,
) -> tuple[str, dict[str, int]]:
    """Run the full transformer chain and return ``(markdown, fallbacks)``."""
    lines = markdown.split("\n")
    fallbacks: dict[str, int] = {}

    lines = heading_normalizer.transform(lines, fallbacks)
    lines = unnumbered_heading_detector.transform(lines, fallbacks)
    if monospace_ranges:
        lines = listing_wrapper.transform(lines, fallbacks, monospace_ranges)
    lines = html_table_converter.transform(lines, fallbacks)
    lines = caption_folder.transform(lines, fallbacks)
    lines = inline_normalizer.transform(lines, fallbacks)

    return "\n".join(lines), fallbacks


__all__ = [
    "caption_folder",
    "heading_normalizer",
    "html_table_converter",
    "inline_normalizer",
    "listing_wrapper",
    "postprocess",
    "unnumbered_heading_detector",
]
