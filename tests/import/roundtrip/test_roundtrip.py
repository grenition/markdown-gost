"""Roundtrip regression tests (T039).

For every screenshot case we render md → docx → import → md and assert
that the structural profile didn't *lose* anything important. Exact text
isn't compared — neither our exporter nor pandoc's importer is idempotent,
and that's fine.

Tolerances (per task spec):
* headings, tables, images, equations — **0 losses** (extras are OK);
* fenced code blocks — ±1 (monospace heuristic can over/under-fire on
  synthetic cases).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _pipeline import CaseInputs
from roundtrip_harness import RoundtripResult, run_roundtrip


@pytest.mark.requires_pandoc
def test_roundtrip(screenshot_case: CaseInputs | None, tmp_path: Path) -> None:
    if screenshot_case is None:
        pytest.skip("no screenshot cases discovered")

    result = run_roundtrip(screenshot_case, tmp_path)

    _assert_headings(result, screenshot_case.name)
    _assert_no_loss(result, "tables", screenshot_case.name)
    _assert_no_loss(result, "images", screenshot_case.name)
    _assert_no_loss(result, "equations", screenshot_case.name)
    _assert_code_blocks(result, screenshot_case.name)


def _assert_headings(result: RoundtripResult, case_name: str) -> None:
    src = result.source.headings_by_level
    rt = result.roundtripped.headings_by_level
    for level, expected in src.items():
        actual = rt.get(level, 0)
        if actual < expected:
            raise AssertionError(
                f"{case_name}: lost headings at level {level} "
                f"(source={expected}, roundtripped={actual})"
            )


def _assert_no_loss(result: RoundtripResult, attr: str, case_name: str) -> None:
    src = getattr(result.source, attr)
    rt = getattr(result.roundtripped, attr)
    if rt < src:
        raise AssertionError(
            f"{case_name}: lost {attr} (source={src}, roundtripped={rt})\n"
            f"Imported Markdown:\n{result.roundtripped_markdown}"
        )


def _assert_code_blocks(result: RoundtripResult, case_name: str) -> None:
    src = result.source.code_blocks
    rt = result.roundtripped.code_blocks
    if abs(rt - src) > 1:
        raise AssertionError(
            f"{case_name}: code-block delta out of tolerance "
            f"(source={src}, roundtripped={rt}, allowed=±1)"
        )
