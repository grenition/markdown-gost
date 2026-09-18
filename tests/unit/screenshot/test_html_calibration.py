"""Unit coverage for the HTML calibration CLI."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import html_calibration
import pytest


def test_report_only_returns_failure_when_a_case_cannot_be_calibrated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    args = argparse.Namespace(
        artifacts_dir=tmp_path,
        reference=tmp_path / "reference.json",
        case=None,
        measure=None,
        report_only=True,
    )
    case = SimpleNamespace(name="broken", html_enabled=True)

    monkeypatch.setattr(html_calibration, "_parse_args", lambda: args)
    monkeypatch.setattr(
        html_calibration,
        "detect_html_runtime",
        lambda: SimpleNamespace(available=True, reason="available"),
    )
    monkeypatch.setattr(html_calibration, "discover_cases", lambda _root: [case])
    monkeypatch.setattr(
        html_calibration,
        "_calibrate_case",
        lambda _case, _root: (_ for _ in ()).throw(RuntimeError("broken case")),
    )

    assert html_calibration.main() == 1
