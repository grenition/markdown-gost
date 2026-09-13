"""Shared semantic preparation for DOCX and native preview."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields

from markdown_gost.config.schema import Config
from markdown_gost.core import ast
from markdown_gost.render.numberer import Numberer


def text_of(node: ast.Node) -> str:
    if isinstance(node, ast.Text):
        return node.text
    if isinstance(node, ast.InlineCode):
        return node.code
    return "".join(text_of(child) for child in getattr(node, "children", []))


def prepare_document(document: ast.Document, config: Config) -> ast.Document:
    """Resolve forward references without mutating the caller's AST."""
    document = deepcopy(document)
    numberer = Numberer()
    targets: dict[str, str] = {}
    captioned = False
    for node in document.children:
        label: str | None = None
        if isinstance(node, ast.Caption):
            captioned = True
            continue
        if isinstance(node, ast.AppendixStart):
            label = f"Приложение {numberer.start_appendix()}"
        elif isinstance(node, ast.AppendixEnd):
            numberer.end_appendix()
        elif isinstance(node, ast.Heading):
            raw = text_of(node)
            structural = (
                node.level == 1
                and not node.numbered
                and raw.upper() in config.headings.structural_titles
            )
            label = raw
            if not structural and config.headings.numbering != "none":
                number = numberer.bump_heading(node.level)
                if node.numbered:
                    label = f"Раздел {number}"
        else:
            target: ast.Node = node
            if (
                isinstance(node, ast.Paragraph)
                and len(node.children) == 1
                and isinstance(node.children[0], ast.Image)
            ):
                target = node.children[0]
            category = {ast.Image: "image", ast.Table: "table", ast.Equation: "equation"}.get(
                type(target)
            )
            if isinstance(node, ast.Listing) and captioned:
                category = "listing"
            if category:
                number = numberer.format_number(category, numberer.allocate(category))
                labels = {"image": "Рисунок", "table": "Таблица", "listing": "Листинг"}
                if category == "equation":
                    number = f"({number})" if config.equation.parentheses else number
                    label = f"Формула {number}"
                else:
                    label = f"{labels[category]} {number}"
                if target.identifier:
                    targets[target.identifier] = label
        if label is not None and node.identifier:
            targets[node.identifier] = label
        captioned = False

    def resolve(node: ast.Node) -> ast.Node:
        if isinstance(node, ast.Reference):
            if node.name not in targets:
                raise ValueError(f"unknown or unnumbered reference target: {node.name}")
            return ast.Link(url=f"#{node.name}", children=[ast.Text(text=targets[node.name])])
        for field in fields(node):
            value = getattr(node, field.name)
            if isinstance(value, list):
                setattr(
                    node,
                    field.name,
                    [resolve(child) if isinstance(child, ast.Node) else child for child in value],
                )
        return node

    resolve(document)
    return document
