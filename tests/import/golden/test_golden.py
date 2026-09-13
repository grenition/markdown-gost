"""Golden tests for the import pipeline (T038).

Each fixture directory is one parametrized case; the harness reads the
docx, runs the full pipeline, and diffs the resulting markdown against
``expected.md``.  See ``README.md`` for how to add a case or regenerate
a baseline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from golden_harness import GoldenCase, run_import_golden


@pytest.mark.requires_pandoc
def test_golden(golden_case: GoldenCase, tmp_path: Path) -> None:
    if golden_case.name == "<no cases>":
        pytest.skip("no golden cases discovered")
    run_import_golden(golden_case, tmp_path)
