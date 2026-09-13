"""Pytest plugin for screenshot tests.

Fixtures
--------
- `screenshot_case`     parametrized; one CaseInputs per discovered case dir
- `unoserver_client`    session-scoped; returns (host, port) once reachability is verified
- `pdf_diff_report`     session-scoped; collects CaseFailure objects, emits _report.pdf

Behavior
--------
- Any subdirectory of `tests/screenshot/` containing `case.md` is treated as a case
- Per-case `meta.yaml` may override `tolerance_pixels` and `dpi`
- Set `MARKDOWN_GOST_UPDATE_BASELINES=1` to (re)generate `expected.pdf` for every case
- Set `MARKDOWN_GOST_SKIP_IF_NO_UNOSERVER=0` to fail (instead of skip) when unoserver is down
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from _pipeline import (
    CaseFailure,
    CaseInputs,
    discover_cases,
    is_unoserver_reachable,
    unoserver_settings,
)
from _report import build_report

SCREENSHOT_ROOT = Path(__file__).parent
ARTIFACTS_DIR = SCREENSHOT_ROOT / "_artifacts"
REPORT_PDF = SCREENSHOT_ROOT / "_report.pdf"


_FAILURES: list[CaseFailure] = []


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "screenshot: visual regression test (DOCX → PDF → pixel diff)"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        item_path = Path(item.fspath)
        if SCREENSHOT_ROOT in item_path.parents or item_path.parent == SCREENSHOT_ROOT:
            item.add_marker(pytest.mark.screenshot)


def _all_cases() -> list[CaseInputs]:
    return discover_cases(SCREENSHOT_ROOT)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "screenshot_case" in metafunc.fixturenames:
        cases = _all_cases()
        if not cases:
            metafunc.parametrize("screenshot_case", [], ids=[])
            return
        metafunc.parametrize(
            "screenshot_case",
            cases,
            ids=[c.name for c in cases],
        )


@pytest.fixture(scope="session")
def unoserver_client() -> tuple[str, int]:
    host, port = unoserver_settings()
    if not is_unoserver_reachable(host, port):
        skip_if_missing = os.environ.get("MARKDOWN_GOST_SKIP_IF_NO_UNOSERVER", "1").lower() in {
            "1",
            "true",
            "yes",
        }
        msg = (
            f"unoserver unreachable at {host}:{port}. "
            "Start the dev stack (`make up`) or run via `make test-in-docker`."
        )
        if skip_if_missing:
            pytest.skip(msg, allow_module_level=True)
        else:
            pytest.fail(msg, pytrace=False)
    return host, port


@pytest.fixture(scope="session")
def pdf_diff_report() -> Iterator[list[CaseFailure]]:
    """Session-scoped accumulator for failures; report PDF is built at session end."""
    _FAILURES.clear()
    if REPORT_PDF.exists():
        REPORT_PDF.unlink()
    yield _FAILURES


def record_failure(failure: CaseFailure) -> None:
    """Used by tests to register a diff failure for the session-end report."""
    _FAILURES.append(failure)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _FAILURES:
        return
    try:
        build_report(_FAILURES, REPORT_PDF)
    except Exception as exc:  # pragma: no cover — best effort
        session.config.get_terminal_writer().line(
            f"[screenshot] failed to build _report.pdf: {exc}", red=True
        )
        return
    tw = session.config.get_terminal_writer()
    tw.line("")
    tw.line("=" * 70, yellow=True)
    tw.line("Screenshot diffs detected", yellow=True, bold=True)
    tw.line(f"  report: {REPORT_PDF}", yellow=True)
    for failure in _FAILURES:
        tw.line(f"  - {failure.case.name}: {failure.summary}", yellow=True)
    tw.line("=" * 70, yellow=True)
