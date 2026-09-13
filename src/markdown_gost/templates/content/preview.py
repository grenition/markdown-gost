"""Native HTML-preview representation of the ``content`` template."""

from __future__ import annotations

from typing import Any

from markdown_gost.preview_json import JsonValue
from markdown_gost.templates import PreviewTemplateContext


def render_preview(params: dict[str, Any], context: PreviewTemplateContext) -> None:
    """Emit a structural TOC heading and populate its links after layout."""

    title = str(params.get("title") or "")
    if title:
        context.add_block("heading", title, style=_structural_heading_style(context), level=1)

    toc_layout = context.add_block(
        "toc",
        "",
        style=_toc_style(context),
        layout={"dot_leader": bool(params.get("dot_leader", True)), "entries": []},
    )
    assert toc_layout is not None
    toc_page = context.page
    depth = int(params.get("depth", 6))

    def populate_entries() -> None:
        entries = toc_layout["entries"]
        assert isinstance(entries, list)
        for entry in context.index.headings:
            if entry.level > depth or entry.page <= toc_page:
                continue
            toc_entry: dict[str, JsonValue] = {
                "anchor": entry.anchor,
                "level": entry.level,
                "number": entry.number,
                "numbered": entry.numbered,
                "page": entry.page,
                "text": entry.text,
            }
            entries.append(toc_entry)

    context.defer(populate_entries)
    context.add_page_break()


def _structural_heading_style(context: PreviewTemplateContext) -> dict[str, Any]:
    config = context.config
    spec = config.headings.structural
    return {
        "font_family": config.font.family,
        "font_size": spec.size or config.font.size,
        "line_spacing": config.font.line_spacing,
        "alignment": spec.alignment,
        "indent_first_line": "0cm",
        "space_before": spec.space_before,
        "space_after": spec.space_after,
        "page_break_before": spec.page_break_before,
        "keep_with_next": spec.keep_with_next,
        "bold": spec.bold,
        "italic": spec.italic,
        "uppercase": spec.uppercase,
    }


def _toc_style(context: PreviewTemplateContext) -> dict[str, Any]:
    config = context.config
    return {
        "font_family": config.font.family,
        "font_size": config.font.size,
        "line_spacing": config.font.line_spacing,
        "alignment": "left",
        "indent_first_line": "0cm",
        "space_before": "0pt",
        "space_after": "0pt",
    }
