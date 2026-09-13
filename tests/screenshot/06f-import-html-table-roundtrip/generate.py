"""Regenerate ``case.md`` from ``_source.html.md`` through the full postprocessor.

The screenshot harness only knows how to render ``case.md``. To prove the
T046 end-to-end pipeline (raw pandoc ``<table>`` → pipe-table → DOCX → PDF)
we commit:

* ``_source.html.md`` — frozen fixture of what pandoc would emit;
* ``case.md`` — what ``postprocess`` produces from it.

This script keeps the two in sync. Re-run it whenever the postprocessor
changes; commit both files. Manual edits to ``case.md`` will be
overwritten on the next regeneration.
"""

from __future__ import annotations

from pathlib import Path

from markdown_gost.import_.postprocessor import postprocess

HERE = Path(__file__).parent
SOURCE = HERE / "_source.html.md"
TARGET = HERE / "case.md"


def build() -> None:
    raw = SOURCE.read_text(encoding="utf-8")
    converted, fallbacks = postprocess(raw)
    if fallbacks:
        raise RuntimeError(
            f"postprocess produced fallbacks {fallbacks!r} — fixture is broken"
        )
    TARGET.write_text(converted, encoding="utf-8")


if __name__ == "__main__":
    build()
    print(f"wrote {TARGET}")
