"""Pytest plugin for import golden tests (T038, T041).

Discovers fixture directories alongside this file and parametrizes the
single ``test_golden`` function over each.  Skipped when pandoc isn't on
``PATH`` — the rest of the suite skips the same way (see
``tests/integration/test_cli_import_e2e.py``). PDF cases (``input.pdf``)
also require a live unoserver.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from golden_harness import GoldenCase, discover_cases

from markdown_gost.import_.pandoc_runner import DEFAULT_PANDOC_BINARY
from markdown_gost.output.pdf_writer import ping_unoserver

GOLDEN_ROOT = Path(__file__).parent


def _pandoc_available() -> bool:
    binary = os.environ.get("PANDOC_BINARY", DEFAULT_PANDOC_BINARY)
    return shutil.which(binary) is not None


@pytest.fixture(autouse=True)
def _skip_if_no_pandoc(golden_case: GoldenCase) -> None:
    if not _pandoc_available():
        pytest.skip("pandoc is not installed; run inside the dev docker image")
    if golden_case.is_pdf and not ping_unoserver():
        pytest.skip(
            "PDF golden case requires a live unoserver; "
            "run inside the docker-compose stack"
        )


def _all_cases() -> list[GoldenCase]:
    return discover_cases(GOLDEN_ROOT)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "golden_case" in metafunc.fixturenames:
        cases = _all_cases()
        metafunc.parametrize(
            "golden_case",
            cases,
            ids=[c.name for c in cases] or ["<no cases>"],
        )
