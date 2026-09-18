"""Roundtrip harness: case.md → docx → import → markdown (T039).

We reuse the existing screenshot case discovery so any case under
``tests/screenshot/<NN>-.../`` automatically participates. The docx is
produced in-memory through :func:`markdown_gost.convert.convert`; the import side
goes through the real :func:`import_docx` pipeline (which shells out to
``pandoc``).

This module deliberately knows nothing about pytest — the
:mod:`conftest` wires it in.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from markdown_gost.config.loader import load_config_from_path
from markdown_gost.convert import convert
from markdown_gost.import_ import ImportContext, import_docx
from markdown_gost.storage import FilesystemStorage

# tests/screenshot/_pipeline.py is a helper module (leading underscore, not a
# package). Adding the screenshot root to ``sys.path`` lets us reuse its
# ``discover_cases`` / ``CaseInputs`` and keeps case discovery in one place.
_SCREENSHOT_ROOT = Path(__file__).resolve().parents[2] / "screenshot"
if str(_SCREENSHOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCREENSHOT_ROOT))

from profile import StructuralProfile  # noqa: E402  (sibling module)

from _pipeline import CaseInputs, discover_cases  # noqa: E402


@dataclass(frozen=True)
class RoundtripResult:
    """Profiles for the source and the post-roundtrip markdown."""

    source: StructuralProfile
    roundtripped: StructuralProfile
    source_markdown: str
    roundtripped_markdown: str


def discover_screenshot_cases() -> list[CaseInputs]:
    """All screenshot cases — one per directory containing ``case.md``."""
    return discover_cases(_SCREENSHOT_ROOT)


def run_roundtrip(case: CaseInputs, tmp_path: Path) -> RoundtripResult:
    """Render *case* to docx, import it back, and return both profiles."""
    config = load_config_from_path(case.config_path)
    source_md = case.md_path.read_text(encoding="utf-8")
    # Resolve image paths relative to the case directory — case.md uses bare
    # filenames like ``img-landscape.png`` and counts on the CLI to find them
    # next to the source file.
    source_storage = FilesystemStorage(base_dir=case.case_dir)
    docx_bytes = convert(source_md, config, format="docx", storage=source_storage)

    docx_path = tmp_path / "roundtrip.docx"
    docx_path.write_bytes(docx_bytes)

    images_dir = tmp_path / "imgs"
    ctx = ImportContext(
        storage=FilesystemStorage(base_dir=tmp_path),
        images_prefix=None,
        images_dir=images_dir,
    )
    result = import_docx(docx_path, ctx)

    return RoundtripResult(
        source=StructuralProfile.from_markdown(source_md),
        roundtripped=StructuralProfile.from_markdown(result.markdown),
        source_markdown=source_md,
        roundtripped_markdown=result.markdown,
    )


# Cases that are known to break structural counts after a roundtrip. Keep
# this list small (≤2) — adding a third entry should prompt a postprocessor
# fix, not another exemption.
KNOWN_BROKEN: dict[str, str] = {}


__all__ = [
    "KNOWN_BROKEN",
    "RoundtripResult",
    "discover_screenshot_cases",
    "run_roundtrip",
]
