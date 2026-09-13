"""Pytest plugin for the import roundtrip tests (T039).

Discovers screenshot cases (one per ``tests/screenshot/<NN>-…/case.md``)
and parametrizes :func:`test_roundtrip` over them. Skipped when pandoc is
missing — same guard as the rest of ``tests/integration/test_*_import_*``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# Make sibling modules (``harness``, ``profile``) importable from the test file.
sys.path.insert(0, str(Path(__file__).parent))

from roundtrip_harness import KNOWN_BROKEN, discover_screenshot_cases

from markdown_gost.import_.pandoc_runner import DEFAULT_PANDOC_BINARY


def _pandoc_available() -> bool:
    binary = os.environ.get("PANDOC_BINARY", DEFAULT_PANDOC_BINARY)
    return shutil.which(binary) is not None


@pytest.fixture(autouse=True)
def _skip_if_no_pandoc() -> None:
    if not _pandoc_available():
        pytest.skip("pandoc is not installed; run inside the dev docker image")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "screenshot_case" not in metafunc.fixturenames:
        return
    cases = discover_screenshot_cases()
    params: list[pytest.ParameterSet] = []
    for case in cases:
        marks: list[pytest.MarkDecorator] = []
        reason = KNOWN_BROKEN.get(case.name)
        if reason is not None:
            marks.append(pytest.mark.xfail(reason=reason, strict=False))
        params.append(pytest.param(case, marks=marks, id=case.name))
    metafunc.parametrize(
        "screenshot_case",
        params or [pytest.param(None, id="<no cases>")],
    )
