"""Generic screenshot test runner — one parametrized test per discovered case."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from _diff import diff_pages
from _pipeline import (
    ARTIFACTS_DIR,
    CaseFailure,
    CaseInputs,
    HarnessError,
    PageDiff,
    ValidationIssue,
    docx_to_pdf,
    has_blocking_issues,
    pdf_to_images,
    run_md2gost_convert,
    update_baselines_enabled,
)
from _validators.docx import validate_docx
from PIL import Image


def _save_pages(images: list[Image.Image], directory: Path, prefix: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, img in enumerate(images):
        p = directory / f"{prefix}_{i + 1:03d}.png"
        img.save(p)
        paths.append(p)
    return paths


def _ensure_artifact_dir(case: CaseInputs) -> Path:
    """Создать каталог `_artifacts/<case>/`, удалив только diff-подкаталоги.

    Файлы верхнего уровня (`actual.docx`, `actual.pdf`) сохраняются между
    прогонами — это полезные артефакты для ручной отладки. Подкаталоги
    `expected/`, `actual/`, `page_*/` чистятся, чтобы не копились устаревшие
    сравнения.
    """
    target = ARTIFACTS_DIR / case.name
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir() and (
            child.name in {"expected", "actual"} or child.name.startswith("page_")
        ):
            shutil.rmtree(child)
    return target


def test_screenshot_case(
    screenshot_case: CaseInputs,
    unoserver_client: tuple[str, int],
    pdf_diff_report: list[CaseFailure],
) -> None:
    case = screenshot_case
    host, port = unoserver_client

    artifact_dir = _ensure_artifact_dir(case)
    actual_docx = artifact_dir / "actual.docx"
    actual_pdf = artifact_dir / "actual.pdf"

    try:
        run_md2gost_convert(case.md_path, case.config_path, actual_docx)
        docx_to_pdf(actual_docx, actual_pdf, host, port)
    except HarnessError as exc:
        pytest.fail(str(exc), pytrace=False)

    if update_baselines_enabled() or not case.expected_pdf.exists():
        case.expected_pdf.write_bytes(actual_pdf.read_bytes())
        if update_baselines_enabled():
            pytest.skip(f"{case.name}: baseline updated (MARKDOWN_GOST_UPDATE_BASELINES=1)")
        # First-run bootstrap: baseline created, nothing to compare yet.
        pytest.skip(f"{case.name}: baseline created at {case.expected_pdf}")

    # ----- validators (independent of pixel diff) -----------------------
    validation_issues: list[ValidationIssue] = []
    if case.validate_docx:
        validation_issues.extend(validate_docx(actual_docx))

    # ----- pixel diff ----------------------------------------------------
    expected_images = pdf_to_images(case.expected_pdf, dpi=case.dpi)
    actual_images = pdf_to_images(actual_pdf, dpi=case.dpi)

    failure_pages: list[PageDiff] = []
    page_count_mismatch = len(expected_images) != len(actual_images)

    if page_count_mismatch:
        _save_pages(expected_images, artifact_dir / "expected", "expected")
        _save_pages(actual_images, artifact_dir / "actual", "actual")

    if not page_count_mismatch:
        for i, (exp, act) in enumerate(zip(expected_images, actual_images, strict=False)):
            result = diff_pages(exp, act)
            if result.pixels_differ <= case.tolerance_pixels:
                continue

            page_dir = artifact_dir / f"page_{i + 1:03d}"
            page_dir.mkdir(parents=True, exist_ok=True)
            expected_path = page_dir / "expected.png"
            actual_path = page_dir / "actual.png"
            diff_path = page_dir / "diff.png"
            result.expected.save(expected_path)
            result.actual.save(actual_path)
            result.overlay.save(diff_path)

            failure_pages.append(
                PageDiff(
                    index=i,
                    expected_path=expected_path,
                    actual_path=actual_path,
                    diff_path=diff_path,
                    pixels_differ=result.pixels_differ,
                )
            )

    blocking_validation = has_blocking_issues(validation_issues)

    if not (page_count_mismatch or failure_pages or blocking_validation):
        return

    summary_parts: list[str] = []
    if page_count_mismatch:
        summary_parts.append(
            f"page count mismatch: expected={len(expected_images)} actual={len(actual_images)}"
        )
    if failure_pages:
        summary_parts.append(
            f"{len(failure_pages)} page(s) differ "
            f"beyond tolerance={case.tolerance_pixels}px: "
            + ", ".join(f"p{p.index + 1}={p.pixels_differ}px" for p in failure_pages)
        )
    if blocking_validation:
        error_count = sum(1 for i in validation_issues if i.severity.value == "error")
        summary_parts.append(f"{error_count} validation error(s)")
    summary = "; ".join(summary_parts)

    pdf_diff_report.append(
        CaseFailure(
            case=case,
            artifact_dir=artifact_dir,
            pages=failure_pages,
            summary=summary,
            validation_issues=validation_issues,
        )
    )
    pytest.fail(summary, pytrace=False)
