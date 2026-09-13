"""Smoke tests for the docx import pipeline (T040).

Не проверяем качество вывода — проверяем что пайплайн не падает на реальных
«грязных» документах и выдаёт разумный объём текста / счётчиков. Каждый кейс
описан в ``expectations.yaml`` рядом с docx. См. ``README.md`` про политику
хранения фикстур.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from smoke_harness import SmokeCase, run_case


@pytest.mark.requires_pandoc
def test_smoke(smoke_case: SmokeCase | None, tmp_path: Path) -> None:
    if smoke_case is None:
        pytest.skip("no smoke cases discovered")

    outcome = run_case(smoke_case, tmp_path)
    exp = smoke_case.expectations

    if len(outcome.markdown) < exp.min_chars:
        raise AssertionError(
            f"{smoke_case.name}: markdown too short "
            f"(got {len(outcome.markdown)} chars, expected >= {exp.min_chars})"
        )

    if outcome.fallback_total > exp.max_fallbacks:
        raise AssertionError(
            f"{smoke_case.name}: too many fallbacks "
            f"(got {outcome.fallback_total}, allowed <= {exp.max_fallbacks}); "
            f"breakdown={outcome.result.fallbacks}"
        )

    missing = [s for s in exp.must_contain if s not in outcome.markdown]
    if missing:
        raise AssertionError(
            f"{smoke_case.name}: missing required substrings: {missing}"
        )

    deficits: list[str] = []
    for key, threshold in exp.must_have_at_least.items():
        actual = outcome.counts.get(key, 0)
        if actual < threshold:
            deficits.append(f"{key}: got {actual}, expected >= {threshold}")
    if deficits:
        raise AssertionError(
            f"{smoke_case.name}: structural counters below threshold: {deficits}"
        )
