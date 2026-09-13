"""Data classes shared by the import pipeline.

``import_`` is the package name because ``import`` is a reserved word in Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_gost.storage import Storage


@dataclass(frozen=True)
class ImageRef:
    """A binary asset extracted from the source document.

    ``name`` is the flat 32-hex content id (``^[0-9a-f]{32}$``, no extension,
    no original archive name) used as the basename of the storage key /
    markdown link emitted for this image (T043). The bytes live at ``path``
    in the pandoc media tempdir.
    """

    name: str
    path: Path


@dataclass
class ImportResult:
    """Outcome of an import run.

    ``warnings`` records non-fatal degradations surfaced to the caller (CLI
    prints them, API returns them in the JSON envelope). ``fallbacks`` counts
    blocks that pandoc/postprocessor could not classify and which were left in
    raw form, broken down by stage name (e.g. ``"caption"``, ``"listing"``);
    the same counts are also emitted via the ``md2gost_import_fallback_total``
    Prometheus metric in T033+.
    """

    markdown: str
    images: list[ImageRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallbacks: dict[str, int] = field(default_factory=dict)


@dataclass
class ImportContext:
    """Caller-provided wiring for an import run.

    Exactly one of ``images_prefix`` (S3 / Storage key prefix) and
    ``images_dir`` (local directory) is meaningful at any given call site —
    the CLI fills ``images_dir``, the API fills ``images_prefix``. The
    postprocessor (T033+) reads whichever is set when rewriting image refs in
    the markdown.
    """

    storage: Storage
    images_prefix: str | None = None
    images_dir: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
