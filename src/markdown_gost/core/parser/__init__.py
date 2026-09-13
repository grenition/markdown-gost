"""Markdown → AST. Normative grammar: docs/syntax-manifest.md."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import fields
from typing import Any

import yaml
from marko import Markdown, block, inline
from marko.ext.gfm import GFM
from marko.ext.gfm import elements as gfm

from .. import ast
from . import _marko_ext as ext
from .attrs import parse_attributes, parse_image_attrs, parse_size_list, parse_size_value

__all__ = ["parse", "parse_image_attrs"]


def walk(node: ast.Node) -> Iterator[ast.Node]:
    """Walk structural AST fields, including list items and table cells."""
    yield node
    for field in fields(node):
        value = getattr(node, field.name)
        if isinstance(value, list):
            for child in value:
                if isinstance(child, ast.Node):
                    yield from walk(child)


def _text(node: Any) -> str:
    children = getattr(node, "children", "")
    if isinstance(children, str):
        return children
    return "".join(_text(child) for child in children or [])


def _plain(node: ast.Node) -> str:
    if isinstance(node, ast.Text):
        return node.text
    return "".join(_plain(child) for child in getattr(node, "children", []))


def _image_in(node: ast.Node) -> ast.Image | None:
    if isinstance(node, ast.Image):
        return node
    if isinstance(node, ast.Paragraph) and len(node.children) == 1:
        child = node.children[0]
        if isinstance(child, ast.Image):
            return child
    return None


def _apply_attrs(node: ast.Node, attrs: dict[str, str]) -> None:
    image = _image_in(node)
    if image is not None:
        node = image
    allowed = {"id"}
    if isinstance(node, ast.Heading):
        allowed |= {".unnumbered", ".appendix"}
    elif isinstance(node, ast.Image):
        allowed |= {"width", "height"}
    elif isinstance(node, ast.Table):
        allowed |= {"widths", "heights"}
    elif isinstance(node, ast.List) and node.ordered:
        allowed.add("marker")
    unknown = attrs.keys() - allowed
    if unknown:
        raise ValueError(f"unsupported attributes for {type(node).__name__}: {sorted(unknown)}")
    if "id" in attrs:
        if node.identifier is not None:
            raise ValueError("duplicate identifier on object")
        node.identifier = attrs["id"]
    if isinstance(node, ast.Heading):
        node.numbered = ".unnumbered" not in attrs and node.numbered
        node.appendix = ".appendix" in attrs or node.appendix
        if node.appendix and (node.level != 1 or not node.numbered):
            raise ValueError(".appendix requires a level-one heading without .unnumbered")
    elif isinstance(node, ast.Image):
        for name in ("width", "height"):
            if name not in attrs:
                continue
            pair = parse_size_value(attrs[name])
            if pair is None or (pair[1] != "auto" and pair[0] <= 0):
                raise ValueError(f"invalid image {name}: {attrs[name]!r}")
            setattr(node, name, ast.Length(value=pair[0], unit=pair[1]))
    elif isinstance(node, ast.Table):
        for name, count, percent, target in (
            (
                "widths",
                max((len(row.cells) for row in node.rows), default=0),
                True,
                "column_widths",
            ),
            ("heights", len(node.rows), False, "row_heights"),
        ):
            if name in attrs:
                pairs = parse_size_list(
                    attrs[name], expected_count=count, allow_percent=percent, field_name=name
                )
                if any(value <= 0 and unit != "auto" for value, unit in pairs):
                    raise ValueError(f"{name}: sizes must be positive")
                setattr(node, target, [ast.Length(value=value, unit=unit) for value, unit in pairs])
    elif isinstance(node, ast.List) and "marker" in attrs:
        style = attrs["marker"]
        if style not in {
            "arabic",
            "lower-alpha-ru",
            "upper-alpha-ru",
            "lower-alpha-en",
            "upper-alpha-en",
        }:
            raise ValueError(f"unknown list marker: {style}")
        node.marker_style = style


class _AstBuilder:
    def __init__(self) -> None:
        self._md = Markdown(extensions=[GFM, ext.GostExtension])

    def build(self, text: str) -> ast.Document:
        document = ast.Document(children=self._blocks(self._md.parse(text).children))
        document.children = _appendix_scopes(document.children)
        identifiers: set[str] = set()
        for node in walk(document):
            if node.identifier is not None:
                if node.identifier in identifiers:
                    raise ValueError(f"duplicate identifier: {node.identifier}")
                identifiers.add(node.identifier)
        return document

    def _blocks(self, nodes: Sequence[Any]) -> list[ast.BlockNode]:
        out: list[ast.BlockNode] = []
        blank_count = 0
        for node in nodes:
            if isinstance(node, block.BlankLine):
                blank_count += 1
                continue
            if isinstance(node, ext.Caption):
                if not out or blank_count > 1:
                    raise ValueError("caption requires an immediately preceding object")
                target = out[-1]
                kind = {ast.Table: "table", ast.Listing: "listing", ast.Mermaid: "diagram"}.get(
                    type(target)
                )
                if kind is None or (len(out) > 1 and isinstance(out[-2], ast.Caption)):
                    raise ValueError(
                        "caption requires a table, listing or diagram without a caption"
                    )
                _apply_attrs(target, node.attrs)
                out.insert(
                    len(out) - 1,
                    ast.Caption(
                        target=kind,
                        text=node.caption_text,
                        attrs={key: value for key, value in node.attrs.items() if key != "id"},
                    ),
                )
            elif type(node) is ext.AttributeBlock:
                if not out:
                    raise ValueError("attributes require a preceding block")
                _apply_attrs(out[-1], node.attrs)
            else:
                converted = self._block(node)
                if isinstance(converted, list):
                    out.extend(converted)
                elif converted is not None:
                    out.append(converted)
            blank_count = 0
        return out

    def _block(self, node: Any) -> ast.BlockNode | list[ast.BlockNode] | None:
        if isinstance(node, block.Heading | block.SetextHeading):
            heading = ast.Heading(level=node.level, children=self._inlines(node))
            _apply_attrs(heading, getattr(node, "attrs", {}))
            return heading
        if isinstance(node, ext.Equation):
            return ast.Equation(latex=node.latex)
        if isinstance(node, ext.Container):
            return self._container(node)
        if isinstance(node, block.ThematicBreak):
            return ast.ThematicBreak()
        if isinstance(node, block.FencedCode):
            language = node.lang or None
            if language and language.lower() == "mermaid":
                return ast.Mermaid(code=_text(node))
            return ast.Listing(language=language, code=_text(node))
        if isinstance(node, block.CodeBlock):
            return ast.Listing(code=_text(node))
        if isinstance(node, gfm.Table):
            return ast.Table(
                rows=[
                    ast.TableRow(
                        header=index == 0,
                        cells=[
                            ast.TableCell(
                                children=self._inlines(cell), align=cell.align, header=index == 0
                            )
                            for cell in getattr(row, "children", [])
                        ],
                    )
                    for index, row in enumerate(node.children)
                ]
            )
        if isinstance(node, block.List):
            ordered = bool(node.ordered)
            return ast.List(
                ordered=ordered,
                start=node.start or 1,
                marker_style="arabic" if ordered else "bullet",
                delimiter=node.bullet[-1] if ordered else ".",
                items=[
                    ast.ListItem(children=list(self._blocks(getattr(item, "children", []))))
                    for item in node.children
                ],
            )
        if isinstance(node, block.Paragraph):
            return ast.Paragraph(children=self._inlines(node))
        if isinstance(node, block.Quote):
            return self._blocks(node.children)
        if isinstance(node, block.HTMLBlock):
            body = node.body or ""
            if body.strip().startswith("<!--") and body.strip().endswith("-->"):
                return None
            return ast.Paragraph(children=[ast.Text(text=body)])
        return None

    def _container(self, node: ext.Container) -> ast.BlockNode | list[ast.BlockNode]:
        attrs = dict(node.attrs)
        roles = [key for key in attrs if key.startswith(".")]
        if len(roles) != 1:
            raise ValueError("container requires exactly one role")
        role = roles[0]
        attrs.pop(role)
        if role == ".group":
            if attrs:
                raise ValueError(".group does not accept attributes")
            return self._blocks(self._md.parse(node.body).children)
        if role == ".page-break":
            if attrs or node.body.strip():
                raise ValueError(".page-break must be empty without attributes")
            return ast.PageBreak()
        if role == ".bibliography":
            if attrs:
                raise ValueError(".bibliography does not accept attributes")
            return _parse_bibliography(node.body)
        if role != ".template":
            raise ValueError(f"unknown container role: {role}")
        name = attrs.pop("name", "")
        if not name:
            raise ValueError("template requires name")
        try:
            params = yaml.safe_load(node.body) if node.body.strip() else {}
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid template YAML: {exc}") from exc
        if not isinstance(params, dict) or any(not isinstance(key, str) for key in params):
            raise ValueError("template YAML must be a mapping with string keys")
        if attrs.keys() & params.keys():
            raise ValueError("duplicate template parameter")
        for key, value in attrs.items():
            parsed = yaml.safe_load(value)
            params[key] = parsed if isinstance(parsed, bool | int | float) else value
        return ast.TemplateBlock(name=name, params=params)

    def _inlines(self, node: Any) -> list[ast.InlineNode]:
        out: list[ast.InlineNode] = []
        for child in getattr(node, "children", []) or []:
            if isinstance(child, ext.InlineAttributes):
                if out and isinstance(out[-1], ast.Image):
                    _apply_attrs(out[-1], parse_attributes(child.raw))
                else:
                    out.append(ast.Text(text=child.raw))
                continue
            out.append(self._inline(child))
        return out

    def _inline(self, node: Any) -> ast.InlineNode:
        if isinstance(node, ext.InlineEquation):
            return ast.InlineEquation(latex=node.latex)
        if isinstance(node, ext.Citation):
            return ast.Citation(key=node.key)
        if isinstance(node, ext.Underline):
            return ast.Underline(children=self._inlines(node))
        if isinstance(node, inline.Image):
            return ast.Image(src=node.dest or "", alt=_text(node), title=node.title)
        if isinstance(node, inline.CodeSpan):
            return ast.InlineCode(code=_text(node))
        if isinstance(node, inline.LineBreak):
            return ast.LineBreak(soft=node.soft)
        if isinstance(node, inline.Emphasis):
            return ast.Emphasis(children=self._inlines(node))
        if isinstance(node, inline.StrongEmphasis):
            return ast.Strong(children=self._inlines(node))
        if isinstance(node, gfm.Strikethrough):
            return ast.Strikethrough(children=self._inlines(node))
        if isinstance(node, inline.Link | inline.AutoLink):
            children = self._inlines(node)
            if node.dest.startswith("#") and not children:
                return ast.Reference(name=node.dest[1:])
            return ast.Link(
                url=node.dest or "", title=getattr(node, "title", None), children=children
            )
        return ast.Text(text=_text(node))


def _appendix_scopes(nodes: list[ast.BlockNode]) -> list[ast.BlockNode]:
    result: list[ast.BlockNode] = []
    appendix = False
    for node in nodes:
        if isinstance(node, ast.Heading):
            if node.level == 1:
                if appendix:
                    result.append(ast.AppendixEnd())
                appendix = node.appendix
                if appendix:
                    result.append(ast.AppendixStart(title=_plain(node), identifier=node.identifier))
                    continue
            elif appendix:
                node.level -= 1
        result.append(node)
    return result


def _parse_bibliography(code: str) -> ast.Bibliography:
    try:
        loaded = yaml.safe_load(code)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid bibliography YAML: {exc}") from exc
    if loaded is None:
        loaded = []
    if not isinstance(loaded, list):
        raise ValueError("bibliography YAML must be a list of sources")
    sources: list[ast.BibliographySource] = []
    for idx, item in enumerate(loaded, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"bibliography source #{idx} must be a mapping")
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            raise ValueError(f"bibliography source #{idx} must have non-empty id")
        raw_type = item.get("type", "other")
        if not isinstance(raw_type, str) or not raw_type.strip():
            raise ValueError(f"bibliography source {raw_id!r} has invalid type")
        sources.append(
            ast.BibliographySource(
                id=raw_id.strip(),
                type=raw_type.strip(),
                fields={
                    str(key): value for key, value in item.items() if key not in {"id", "type"}
                },
            )
        )
    return ast.Bibliography(sources=sources)


def parse(text: str) -> ast.Document:
    """Parse Markdown using only the current syntax manifest."""
    return _AstBuilder().build(text)
