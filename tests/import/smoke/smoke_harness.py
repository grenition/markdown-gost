"""Smoke test harness (T040).

Discovers smoke cases, loads ``expectations.yaml``, and exposes a single
:func:`run_case` that imports a real docx through the production pipeline
and returns the data needed to evaluate every expectation. Knows nothing
about pytest — :mod:`conftest` wires it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from markdown_gost.core.ast import nodes as ast
from markdown_gost.core.parser import parse
from markdown_gost.import_ import ImportContext, ImportResult, import_docx
from markdown_gost.storage import FilesystemStorage

EXPECTATIONS_FILENAME = "expectations.yaml"
DOCX_FILENAME = "input.docx"


@dataclass(frozen=True)
class Expectations:
    """Thresholds for one smoke case (see ``expectations.yaml`` schema)."""

    min_chars: int = 0
    max_fallbacks: int = 0
    must_contain: list[str] = field(default_factory=list)
    must_have_at_least: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> Expectations:
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            min_chars=int(raw.get("min_chars", 0)),
            max_fallbacks=int(raw.get("max_fallbacks", 0)),
            must_contain=list(raw.get("must_contain") or []),
            must_have_at_least=dict(raw.get("must_have_at_least") or {}),
        )


@dataclass(frozen=True)
class SmokeCase:
    """One case directory."""

    name: str
    case_dir: Path
    docx_path: Path
    expectations: Expectations


@dataclass(frozen=True)
class SmokeOutcome:
    """Numbers computed from an import run, ready for assertions."""

    markdown: str
    fallback_total: int
    counts: dict[str, int]
    result: ImportResult


def discover_smoke_cases(root: Path) -> list[SmokeCase]:
    """All immediate subdirs of *root* that carry ``expectations.yaml``."""
    cases: list[SmokeCase] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        exp_path = entry / EXPECTATIONS_FILENAME
        if not exp_path.is_file():
            continue
        cases.append(
            SmokeCase(
                name=entry.name,
                case_dir=entry,
                docx_path=entry / DOCX_FILENAME,
                expectations=Expectations.from_yaml(exp_path),
            )
        )
    return cases


def run_case(case: SmokeCase, tmp_path: Path) -> SmokeOutcome:
    """Import *case*'s docx and compute structural counters."""
    images_dir = tmp_path / "imgs"
    ctx = ImportContext(
        storage=FilesystemStorage(base_dir=tmp_path),
        images_prefix=None,
        images_dir=images_dir,
    )
    result = import_docx(case.docx_path, ctx)
    counts = _count_blocks(result.markdown)
    return SmokeOutcome(
        markdown=result.markdown,
        fallback_total=sum(result.fallbacks.values()),
        counts=counts,
        result=result,
    )


def _count_blocks(markdown: str) -> dict[str, int]:
    """Best-effort structural counters used by ``must_have_at_least``."""
    document = parse(markdown)
    counts = {"headings": 0, "tables": 0, "images": 0, "equations": 0, "listings": 0}
    _walk(document, counts)
    return counts


def _walk(node: ast.Node, counts: dict[str, int]) -> None:
    if isinstance(node, ast.Heading):
        counts["headings"] += 1
    elif isinstance(node, ast.Table):
        counts["tables"] += 1
    elif isinstance(node, ast.Image):
        counts["images"] += 1
    elif isinstance(node, ast.Equation):
        counts["equations"] += 1
    elif isinstance(node, ast.Listing):
        counts["listings"] += 1

    for child in _children(node):
        _walk(child, counts)


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


__all__ = [
    "DOCX_FILENAME",
    "EXPECTATIONS_FILENAME",
    "Expectations",
    "SmokeCase",
    "SmokeOutcome",
    "discover_smoke_cases",
    "run_case",
]
