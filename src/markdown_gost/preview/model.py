from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from markdown_gost.preview_json import JsonPrimitive, JsonValue


@dataclass(frozen=True)
class PreviewLength:
    value: float
    unit: str
    emu: int

    def to_dict(self) -> dict[str, JsonPrimitive]:
        return {"value": self.value, "unit": self.unit, "emu": self.emu}


@dataclass(frozen=True)
class PreviewMargins:
    top: PreviewLength
    right: PreviewLength
    bottom: PreviewLength
    left: PreviewLength

    def to_dict(self) -> dict[str, dict[str, JsonPrimitive]]:
        return {
            "top": self.top.to_dict(),
            "right": self.right.to_dict(),
            "bottom": self.bottom.to_dict(),
            "left": self.left.to_dict(),
        }


@dataclass(frozen=True)
class PreviewPageGeometry:
    page_size: str
    orientation: str
    width: PreviewLength
    height: PreviewLength
    margins: PreviewMargins
    content_width: PreviewLength
    content_height: PreviewLength

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_size": self.page_size,
            "orientation": self.orientation,
            "width": self.width.to_dict(),
            "height": self.height.to_dict(),
            "margins": self.margins.to_dict(),
            "content_width": self.content_width.to_dict(),
            "content_height": self.content_height.to_dict(),
        }


@dataclass(frozen=True)
class PreviewImageDimension:
    value: float
    unit: str

    def to_dict(self) -> dict[str, JsonPrimitive]:
        return {"value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class PreviewTableDimension:
    value: float
    unit: str

    def to_dict(self) -> dict[str, JsonPrimitive]:
        return {"value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class PreviewInline:
    kind: str
    text: str | None = None
    bold: bool = False
    italic: bool = False
    strike: bool = False
    underline: bool = False
    color: str | None = None
    font_family: str | None = None
    font_size: str | None = None
    mathml: str | None = None
    diagnostic: str | None = None
    href: str | None = None
    src: str | None = None
    asset_path: str | None = None
    alt: str | None = None
    title: str | None = None
    width: PreviewImageDimension | None = None
    height: PreviewImageDimension | None = None
    aspect_ratio: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.text is not None:
            out["text"] = self.text
        if self.bold:
            out["bold"] = True
        if self.italic:
            out["italic"] = True
        if self.strike:
            out["strike"] = True
        if self.underline:
            out["underline"] = True
        if self.color is not None:
            out["color"] = self.color
        if self.font_family is not None:
            out["font_family"] = self.font_family
        if self.font_size is not None:
            out["font_size"] = self.font_size
        if self.mathml is not None:
            out["mathml"] = self.mathml
        if self.diagnostic is not None:
            out["diagnostic"] = self.diagnostic
        if self.href is not None:
            out["href"] = self.href
        if self.src is not None:
            out["src"] = self.src
        if self.asset_path is not None:
            out["asset_path"] = self.asset_path
        if self.alt is not None:
            out["alt"] = self.alt
        if self.title is not None:
            out["title"] = self.title
        if self.width is not None:
            out["width"] = self.width.to_dict()
        if self.height is not None:
            out["height"] = self.height.to_dict()
        if self.aspect_ratio is not None:
            out["aspect_ratio"] = self.aspect_ratio
        return out


@dataclass(frozen=True)
class PreviewTableCell:
    text: str
    inlines: list[PreviewInline] = field(default_factory=list)
    align: str | None = None
    header: bool = False
    col_span: int = 1
    row_span: int = 1

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": self.text,
            "inlines": [inline.to_dict() for inline in self.inlines],
            "header": self.header,
            "col_span": self.col_span,
            "row_span": self.row_span,
        }
        if self.align is not None:
            out["align"] = self.align
        return out


@dataclass(frozen=True)
class PreviewTableRow:
    cells: list[PreviewTableCell] = field(default_factory=list)
    header: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header,
            "cells": [cell.to_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class PreviewBlock:
    kind: str
    id: str
    page: int
    text: str
    inlines: list[PreviewInline] = field(default_factory=list)
    style: dict[str, JsonPrimitive] = field(default_factory=dict)
    mathml: str | None = None
    diagnostic: str | None = None
    anchor: str | None = None
    level: int | None = None
    numbered: bool | None = None
    number: str | None = None
    list_type: str | None = None
    marker: str | None = None
    marker_separator: str | None = None
    continuation: bool | None = None
    caption: str | None = None
    rows: list[PreviewTableRow] | None = None
    column_widths: list[PreviewTableDimension] | None = None
    row_heights: list[PreviewTableDimension] | None = None
    language: str | None = None
    layout: dict[str, JsonValue] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "id": self.id,
            "page": self.page,
            "text": self.text,
            "inlines": [inline.to_dict() for inline in self.inlines],
            "style": dict(self.style),
        }
        if self.mathml is not None:
            out["mathml"] = self.mathml
        if self.diagnostic is not None:
            out["diagnostic"] = self.diagnostic
        if self.anchor is not None:
            out["anchor"] = self.anchor
        if self.level is not None:
            out["level"] = self.level
        if self.numbered is not None:
            out["numbered"] = self.numbered
        if self.number is not None:
            out["number"] = self.number
        if self.list_type is not None:
            out["list_type"] = self.list_type
        if self.marker is not None:
            out["marker"] = self.marker
        if self.marker_separator is not None:
            out["marker_separator"] = self.marker_separator
        if self.continuation is not None:
            out["continuation"] = self.continuation
        if self.caption is not None:
            out["caption"] = self.caption
        if self.rows is not None:
            out["rows"] = [row.to_dict() for row in self.rows]
        if self.column_widths is not None:
            out["column_widths"] = [width.to_dict() for width in self.column_widths]
        if self.row_heights is not None:
            out["row_heights"] = [height.to_dict() for height in self.row_heights]
        if self.language is not None:
            out["language"] = self.language
        if self.layout is not None:
            out["layout"] = self.layout
        return out


@dataclass(frozen=True)
class PreviewPage:
    number: int
    blocks: list[PreviewBlock] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass(frozen=True)
class PreviewAnchor:
    kind: str
    anchor: str
    page: int
    block_id: str
    text: str
    level: int

    def to_dict(self) -> dict[str, JsonPrimitive]:
        return {
            "kind": self.kind,
            "anchor": self.anchor,
            "page": self.page,
            "block_id": self.block_id,
            "text": self.text,
            "level": self.level,
        }


@dataclass(frozen=True)
class PreviewDocument:
    geometry: PreviewPageGeometry
    total_pages: int
    pages: list[PreviewPage]
    anchors: list[PreviewAnchor] = field(default_factory=list)
    version: str = "preview-model.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "geometry": self.geometry.to_dict(),
            "total_pages": self.total_pages,
            "pages": [page.to_dict() for page in self.pages],
            "anchors": [anchor.to_dict() for anchor in self.anchors],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
