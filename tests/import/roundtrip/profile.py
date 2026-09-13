"""Structural profile of a markdown document (T039).

The roundtrip test compares *counts*, not text. ``StructuralProfile`` exposes
just enough information to detect "we lost a heading / a table / a formula
along the way" while staying immune to whitespace, attribute, and ordering
churn that md → docx → md inevitably introduces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from markdown_gost.core.ast import nodes as ast
from markdown_gost.core.parser import parse


@dataclass(frozen=True)
class StructuralProfile:
    """Counts of structurally significant blocks in a document."""

    headings_by_level: dict[int, int] = field(default_factory=dict)
    tables: int = 0
    images: int = 0
    equations: int = 0
    code_blocks: int = 0

    @classmethod
    def from_markdown(cls, markdown: str) -> StructuralProfile:
        return cls.from_document(parse(markdown))

    @classmethod
    def from_document(cls, document: ast.Document) -> StructuralProfile:
        counts: _Counts = _Counts()
        _walk(document, counts)
        return cls(
            headings_by_level=dict(counts.headings),
            tables=counts.tables,
            images=counts.images,
            equations=counts.equations,
            code_blocks=counts.code_blocks,
        )


@dataclass
class _Counts:
    headings: dict[int, int] = field(default_factory=dict)
    tables: int = 0
    images: int = 0
    equations: int = 0
    code_blocks: int = 0


def _walk(node: ast.Node, counts: _Counts) -> None:
    if isinstance(node, ast.Heading):
        counts.headings[node.level] = counts.headings.get(node.level, 0) + 1
    elif isinstance(node, ast.Table):
        counts.tables += 1
        # Our docx exporter wraps block equations into a 2-column numbering
        # table (formula | "(N)") and pandoc re-imports that as a pipe table
        # with inline math. Treat such tables as equations too so the count
        # survives the roundtrip — without this every block equation would
        # appear "lost" even though the math itself is intact.
        counts.equations += _table_equation_rows(node)
    elif isinstance(node, ast.Image):
        counts.images += 1
    elif isinstance(node, ast.Equation):
        counts.equations += 1
    elif isinstance(node, ast.Listing):
        counts.code_blocks += 1

    # Recurse into every container variant our AST exposes.
    for child in _children(node):
        _walk(child, counts)


def _table_equation_rows(table: ast.Table) -> int:
    """Count data rows whose first cell carries an inline equation."""
    count = 0
    for row in table.rows:
        if row.header or not row.cells:
            continue
        if _contains_inline_equation(row.cells[0]):
            count += 1
    return count


def _contains_inline_equation(node: ast.Node) -> bool:
    if isinstance(node, ast.InlineEquation):
        return True
    children = getattr(node, "children", None)
    if isinstance(children, list):
        for child in children:
            if isinstance(child, ast.Node) and _contains_inline_equation(child):
                return True
    return False


def _children(node: ast.Node) -> list[ast.Node]:
    out: list[ast.Node] = []
    children = getattr(node, "children", None)
    if isinstance(children, list):
        out.extend(c for c in children if isinstance(c, ast.Node))
    if isinstance(node, ast.Table):
        for row in node.rows:
            out.extend(row.cells)
    if isinstance(node, ast.List):
        out.extend(node.items)
    return out


__all__ = ["StructuralProfile"]
