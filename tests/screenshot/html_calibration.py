"""Run native HTML preview calibration against committed PDF oracles."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from _html_pipeline import (
    HarnessError,
    HtmlCaseInputs,
    HtmlCaseMetrics,
    build_calibration_summary,
    calibrate_page_sets,
    capture_html_pages,
    detect_html_runtime,
    discover_cases,
    regression_failures,
    render_html_case,
)
from _pipeline import pdf_to_images

SCREENSHOT_ROOT = Path(__file__).parent
DEFAULT_ARTIFACT_ROOT = SCREENSHOT_ROOT / "_artifacts" / "html-calibration"
DEFAULT_REFERENCE = SCREENSHOT_ROOT / "html-calibration-reference.json"


def main() -> int:
    args = _parse_args()
    runtime = detect_html_runtime()
    if not runtime.available:
        print(f"HTML calibration runtime unavailable: {runtime.reason}")
        return 2

    cases = [case for case in discover_cases(SCREENSHOT_ROOT) if case.html_enabled]
    if args.case:
        requested = set(args.case)
        discovered = {case.name for case in cases}
        missing = sorted(requested - discovered)
        if missing:
            print("Requested case(s) are not HTML-enabled or do not exist: " + ", ".join(missing))
            return 2
        cases = [case for case in cases if case.name in requested]

    artifact_root = args.artifacts_dir.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    metrics: list[HtmlCaseMetrics] = []
    errors: list[dict[str, str]] = []
    for case in cases:
        try:
            metrics.append(_calibrate_case(case, artifact_root))
        except Exception as exc:  # keep later cases and emit a complete report
            errors.append(
                {
                    "case": case.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    summary = build_calibration_summary(metrics)
    summary["errors"] = errors
    summary_path = artifact_root / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path = artifact_root / "summary.md"
    markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")
    _print_summary(summary, summary_path)

    failures = [f"{item['case']} calibration error: {item['error']}" for item in errors]
    if args.report_only:
        if failures:
            print("\nHTML calibration FAILED:")
            for failure in failures:
                print(f"  - {failure}")
            print(f"  artifacts: {artifact_root}")
            return 1
        return 0

    try:
        reference = _load_reference(args.reference)
    except HarnessError as exc:
        failures.append(str(exc))
    else:
        failures.extend(regression_failures(summary, reference))
    if failures:
        print("\nHTML calibration FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"  artifacts: {artifact_root}")
        return 1
    print("HTML calibration passed reviewed regression thresholds.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render every HTML-enabled screenshot case with Playwright and "
            "compare it to the committed expected.pdf oracle."
        )
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help=f"artifact root (default: {DEFAULT_ARTIFACT_ROOT})",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
        help=f"reviewed metric reference (default: {DEFAULT_REFERENCE})",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="run one HTML-enabled case; repeat for multiple cases",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="write all metrics/artifacts without applying regression thresholds",
    )
    return parser.parse_args()


def _calibrate_case(
    case: HtmlCaseInputs,
    artifact_root: Path,
) -> HtmlCaseMetrics:
    if not case.case.expected_pdf.exists():
        raise HarnessError(f"missing PDF oracle: {case.case.expected_pdf}")
    artifact_dir = artifact_root / case.name
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    actual_html = artifact_dir / "actual.html"
    render_html_case(case, actual_html)
    expected_pages = pdf_to_images(case.case.expected_pdf, dpi=case.html_dpi)
    actual_pages = capture_html_pages(actual_html, case)
    return calibrate_page_sets(
        case.name,
        expected_pages,
        actual_pages,
        artifact_dir,
    )


def _load_reference(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HarnessError(
            f"missing calibration reference: {path}; use --report-only to "
            "capture metrics before establishing a reviewed reference"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"invalid calibration reference {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HarnessError(f"invalid calibration reference {path}: expected object")
    return payload


def _summary_markdown(summary: dict[str, Any]) -> str:
    aggregate = summary["aggregate"]
    lines = [
        "# HTML preview calibration",
        "",
        (
            f"Pages: {aggregate['actual_pages']}/{aggregate['expected_pages']}; "
            f"page-count mismatches: {aggregate['page_count_mismatches']}; "
            f"layout differing pixels: {aggregate['differing_pixels']} "
            f"({aggregate['differing_rate']:.6%}); raw differing pixels: "
            f"{aggregate['raw_differing_pixels']}."
        ),
        "",
        "| Case | Pages HTML/PDF | Differing pixels | Rate | Worst page |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in summary["cases"]:
        lines.append(
            f"| {case['case']} | {case['actual_pages']}/{case['expected_pages']} "
            f"| {case['differing_pixels']} | {case['differing_rate']:.6%} "
            f"| {case['worst_page_rate']:.6%} |"
        )
    if summary.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in summary["errors"]:
            lines.append(f"- {error['case']}: {error['error']}")
    return "\n".join(lines) + "\n"


def _print_summary(summary: dict[str, Any], summary_path: Path) -> None:
    aggregate = summary["aggregate"]
    print("HTML preview calibration")
    for case in summary["cases"]:
        print(
            f"  {case['case']:<34} "
            f"pages={case['actual_pages']}/{case['expected_pages']} "
            f"diff={case['differing_pixels']:>7} "
            f"rate={case['differing_rate']:.4%}"
        )
    print(
        "  aggregate "
        f"pages={aggregate['actual_pages']}/{aggregate['expected_pages']} "
        f"diff={aggregate['differing_pixels']} "
        f"rate={aggregate['differing_rate']:.4%} "
        f"worst_page={aggregate['worst_page_rate']:.4%}"
    )
    print(f"  summary: {summary_path}")


if __name__ == "__main__":
    raise SystemExit(main())
