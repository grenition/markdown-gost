"""Run native HTML preview calibration against committed PDF oracles."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image
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
    if args.measure:
        return _measure_cases(args.measure, args.artifacts_dir.resolve())

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
    parser.add_argument(
        "--measure",
        action="append",
        metavar="CASE",
        help=(
            "print ink-band geometry (rows: y-range + leftmost ink column) for "
            "existing artifacts of CASE (repeatable); no rendering, no gates"
        ),
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


def _measure_cases(names: list[str], artifact_root: Path) -> int:
    """Print ink-band geometry for existing calibration artifacts.

    Debug helper for parity work: per page, rows of ink grouped into bands
    with their leftmost/rightmost ink column, for both the PDF oracle and
    the rendered HTML. Pixel pitch between band tops ≈ line pitch.
    """

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - debug mode only
        print("Pillow unavailable: --measure needs PIL")
        return 2
    missing = [name for name in names if not (artifact_root / name).exists()]
    if missing:
        print("No artifacts for: " + ", ".join(missing))
        return 2
    for name in names:
        dpi = _case_dpi(name)
        print(f"### {name} (dpi={dpi}; px→pt: ×{72 / dpi:.2f})")
        for page_dir in sorted((artifact_root / name).glob("page_*")):
            print(f"== {page_dir.name} ==")
            for label, png in (
                ("expected_pdf", page_dir / "expected_pdf.png"),
                ("actual_html", page_dir / "actual_html.png"),
            ):
                if not png.exists():
                    continue
                print(f"  [{label}]")
                for y0, y1, x0, x1 in _ink_bands(Image.open(png)):
                    print(
                        f"    y {y0:>4}-{y1:>4} (h={y1 - y0 + 1:>3}) "
                        f"x {x0:>4}-{x1:>4}"
                    )
        pdf = SCREENSHOT_ROOT / name / "expected.pdf"
        boxes = _pdf_word_boxes(pdf)
        if boxes:
            print("  [expected.pdf word boxes, pt]")
            for x_min, y_min, word in boxes[:40]:
                print(f"    x={x_min:>7.2f} y={y_min:>7.2f} {word}")
    return 0


def _case_dpi(name: str) -> int:
    meta = SCREENSHOT_ROOT / name / "meta.yaml"
    if not meta.exists():
        return 100
    match = re.search(r"dpi:\s*(\d+)", meta.read_text(encoding="utf-8"))
    return int(match.group(1)) if match else 100


def _ink_bands(image: Image.Image) -> list[tuple[int, int, int, int]]:
    gray = image.convert("L")
    width, height = gray.size
    data = list(gray.getdata())
    threshold = 200
    spans: list[tuple[int, int]] = []
    band_start: int | None = None
    gap = 0
    for y in range(height):
        if any(data[y * width + x] < threshold for x in range(0, width, 2)):
            if band_start is None:
                band_start = y
            gap = 0
        elif band_start is not None:
            gap += 1
            if gap >= 3:
                spans.append((band_start, y - gap + 1))
                band_start = None
                gap = 0
    if band_start is not None:
        spans.append((band_start, height - 1))
    out: list[tuple[int, int, int, int]] = []
    for y0, y1 in spans:
        x_left = next(
            x
            for x in range(width)
            if any(data[y * width + x] < threshold for y in range(y0, y1 + 1))
        )
        x_right = next(
            x
            for x in range(width - 1, -1, -1)
            if any(data[y * width + x] < threshold for y in range(y0, y1 + 1))
        )
        out.append((y0, y1, x_left, x_right))
    return out


def _pdf_word_boxes(pdf: Path) -> list[tuple[float, float, str]]:
    if not pdf.exists():
        return []
    try:
        completed = subprocess.run(
            ["pdftotext", "-bbox", str(pdf), "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    boxes: list[tuple[float, float, str]] = []
    for match in re.finditer(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)"[^>]*>([^<]+)</word>',
        completed.stdout,
    ):
        boxes.append((float(match.group(1)), float(match.group(2)), match.group(3)))
    return boxes


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
