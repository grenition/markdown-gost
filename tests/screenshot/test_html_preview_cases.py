"""HTML preview parity as part of the generic screenshot gate."""

from __future__ import annotations

import pytest
from _html_pipeline import (
    HTML_RUNTIME_STRICT_ENV,
    HarnessError,
    capture_html_pages,
    compare_page_sets,
    detect_html_runtime,
    html_case_from_screenshot_case,
    is_critical_html_failure,
    prepare_artifact_dir,
    render_html_case,
    strict_runtime_enabled,
)
from _pipeline import (
    CaseFailure,
    CaseInputs,
    pdf_to_images,
    update_baselines_enabled,
)
from conftest import ARTIFACTS_DIR


@pytest.fixture(scope="session")
def html_runtime() -> None:
    runtime = detect_html_runtime()
    if runtime.available:
        return

    message = (
        f"HTML screenshot runtime unavailable: {runtime.reason}. "
        f"Set {HTML_RUNTIME_STRICT_ENV}=1 to fail instead of skip."
    )
    if strict_runtime_enabled():
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)


def test_html_preview_screenshot_case(
    screenshot_case: CaseInputs,
    html_runtime: None,
    pdf_diff_report: list[CaseFailure],
) -> None:
    if update_baselines_enabled():
        pytest.skip("HTML parity uses existing expected.pdf baselines")
    if not screenshot_case.expected_pdf.exists():
        pytest.skip(f"{screenshot_case.name}: missing expected.pdf baseline")

    case = html_case_from_screenshot_case(screenshot_case)
    if not case.html_enabled:
        pytest.skip(f"{case.name}: html_enabled=false")

    artifact_dir = prepare_artifact_dir(ARTIFACTS_DIR, case.name)
    actual_html = artifact_dir / "actual.html"

    try:
        render_html_case(case, actual_html)
        expected_pdf_pages = pdf_to_images(
            screenshot_case.expected_pdf,
            dpi=case.html_dpi,
        )
        actual_html_pages = capture_html_pages(actual_html, case)
    except HarnessError as exc:
        pytest.fail(str(exc), pytrace=False)

    failure = compare_page_sets(
        case,
        expected_pdf_pages,
        actual_html_pages,
        artifact_dir,
    )
    if failure is None:
        return

    pdf_diff_report.append(failure)
    if case.strict_pixels or is_critical_html_failure(failure):
        pytest.fail(failure.summary, pytrace=False)
