"""build_report should emit a validation-issues page when a CaseFailure has issues."""

from __future__ import annotations

from pathlib import Path


def test_build_report_renders_validation_only_failure(tmp_path: Path) -> None:
    from _pipeline import CaseFailure, CaseInputs, ValidationIssue, ValidationSeverity
    from _report import build_report

    case_dir = tmp_path / "case-x"
    case_dir.mkdir()
    case = CaseInputs(
        name="case-x",
        case_dir=case_dir,
        md_path=case_dir / "case.md",
        config_path=case_dir / "config.yaml",
        expected_pdf=case_dir / "expected.pdf",
        tolerance_pixels=50,
        dpi=100,
        validate_docx=True,
    )
    failure = CaseFailure(
        case=case,
        artifact_dir=tmp_path,
        pages=[],
        summary="docx validation failed",
        validation_issues=[
            ValidationIssue(
                validator="docx",
                severity=ValidationSeverity.ERROR,
                code="docx.rels.broken",
                message="missing target media/x.png",
                location="word/_rels/document.xml.rels",
            ),
        ],
    )

    out_pdf = tmp_path / "_report.pdf"
    build_report([failure], out_pdf)

    assert out_pdf.exists()
    assert out_pdf.read_bytes()[:4] == b"%PDF"


def test_build_report_renders_summary_only_failure(tmp_path: Path) -> None:
    from _pipeline import CaseFailure, CaseInputs
    from _report import build_report

    case_dir = tmp_path / "case-pages"
    case_dir.mkdir()
    case = CaseInputs(
        name="case-pages",
        case_dir=case_dir,
        md_path=case_dir / "case.md",
        config_path=case_dir / "config.yaml",
        expected_pdf=case_dir / "expected.pdf",
        tolerance_pixels=50,
        dpi=100,
        validate_docx=True,
    )
    failure = CaseFailure(
        case=case,
        artifact_dir=tmp_path,
        pages=[],
        summary="HTML page count mismatch: expected_pdf=4 actual_html=3",
        validation_issues=[],
    )

    out_pdf = tmp_path / "_report.pdf"
    build_report([failure], out_pdf)

    assert out_pdf.exists()
    assert out_pdf.read_bytes()[:4] == b"%PDF"


def test_build_report_renders_pixel_and_validation_pages(tmp_path: Path) -> None:
    from _pipeline import (
        CaseFailure,
        CaseInputs,
        PageDiff,
        ValidationIssue,
        ValidationSeverity,
    )
    from _report import build_report
    from PIL import Image

    case_dir = tmp_path / "case-y"
    case_dir.mkdir()
    img = Image.new("RGB", (50, 50), (255, 255, 255))
    exp = tmp_path / "expected.png"
    act = tmp_path / "actual.png"
    diff = tmp_path / "diff.png"
    img.save(exp)
    img.save(act)
    img.save(diff)

    case = CaseInputs(
        name="case-y",
        case_dir=case_dir,
        md_path=case_dir / "case.md",
        config_path=case_dir / "config.yaml",
        expected_pdf=case_dir / "expected.pdf",
        tolerance_pixels=50,
        dpi=100,
        validate_docx=True,
    )
    failure = CaseFailure(
        case=case,
        artifact_dir=tmp_path,
        pages=[
            PageDiff(
                index=0,
                expected_path=exp,
                actual_path=act,
                diff_path=diff,
                pixels_differ=123,
            )
        ],
        summary="combined",
        validation_issues=[
            ValidationIssue(
                validator="docx",
                severity=ValidationSeverity.WARNING,
                code="docx.xsd.unavailable",
                message="XSD bundle not installed",
                location=None,
            )
        ],
    )

    out_pdf = tmp_path / "_report.pdf"
    build_report([failure], out_pdf)

    assert out_pdf.exists()
    assert out_pdf.read_bytes()[:4] == b"%PDF"
