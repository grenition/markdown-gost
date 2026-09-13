"""Pytest plugin for the import smoke tests (T040).

Discovers cases under ``tests/import/smoke/<NN>-…/``. A case is any directory
containing ``expectations.yaml``; the actual ``input.docx`` is **not**
committed (see ``.gitignore``) and individual cases are skipped when their
fixture is missing locally — so CI without the private archive still passes.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from smoke_harness import SmokeCase, discover_smoke_cases

from markdown_gost.import_.pandoc_runner import DEFAULT_PANDOC_BINARY


def _pandoc_available() -> bool:
    binary = os.environ.get("PANDOC_BINARY", DEFAULT_PANDOC_BINARY)
    return shutil.which(binary) is not None


@pytest.fixture(autouse=True)
def _skip_if_no_pandoc() -> None:
    if not _pandoc_available():
        pytest.skip("pandoc is not installed; run inside the dev docker image")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "smoke_case" not in metafunc.fixturenames:
        return
    cases = discover_smoke_cases(Path(__file__).parent)
    params: list[pytest.ParameterSet] = []
    for case in cases:
        marks: list[pytest.MarkDecorator] = []
        if not case.docx_path.is_file():
            marks.append(
                pytest.mark.skip(
                    reason=(
                        f"fixture missing: drop a real .docx at "
                        f"{case.docx_path.relative_to(Path(__file__).parent.parent.parent.parent)} "
                        f"(see tests/import/smoke/README.md)"
                    )
                )
            )
        params.append(pytest.param(case, marks=marks, id=case.name))
    metafunc.parametrize(
        "smoke_case",
        params or [pytest.param(None, id="<no cases>")],
    )


__all__ = ["SmokeCase"]
