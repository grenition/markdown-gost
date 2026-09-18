"""Unit coverage for HTML screenshot parity harness internals."""

from __future__ import annotations

from pathlib import Path

from _html_pipeline import (
    BASIC_RENDERER_CASES,
    DEFAULT_HTML_DPI,
    DEFAULT_HTML_TOLERANCE_PIXELS,
    DEFAULT_VIEWPORT_HEIGHT,
    DEFAULT_VIEWPORT_WIDTH,
    HtmlCaseInputs,
    HtmlCaseMetrics,
    _normalize_locator_screenshot,
    build_calibration_summary,
    calibrate_page_sets,
    compare_page_sets,
    detect_html_renderer,
    discover_cases,
    is_critical_html_failure,
    measure_html_page,
    prepare_artifact_dir,
    regression_failures,
    render_html_case,
    strict_pixel_diff_enabled,
)
from _pipeline import CaseInputs
from PIL import Image


def _write_case(root: Path, name: str, meta: str | None = None) -> Path:
    case_dir = root / name
    case_dir.mkdir(parents=True)
    (case_dir / "case.md").write_text("# Title\n", encoding="utf-8")
    (case_dir / "config.yaml").write_text("preset: gost-7-32-2017\n", encoding="utf-8")
    if meta is not None:
        (case_dir / "meta.yaml").write_text(meta, encoding="utf-8")
    return case_dir


def _case_inputs(case_dir: Path, *, tolerance: int = 0, dpi: int = 100) -> CaseInputs:
    return CaseInputs(
        name=case_dir.name,
        case_dir=case_dir,
        md_path=case_dir / "case.md",
        config_path=case_dir / "config.yaml",
        expected_pdf=case_dir / "expected.pdf",
        tolerance_pixels=tolerance,
        dpi=dpi,
    )


def _case(tmp_path: Path, *, tolerance: int = 0) -> HtmlCaseInputs:
    case_dir = tmp_path / "01-basic"
    case_dir.mkdir(exist_ok=True)
    return HtmlCaseInputs(
        case=_case_inputs(case_dir, tolerance=tolerance),
        html_enabled=True,
        html_tolerance_pixels=tolerance,
        html_dpi=100,
        viewport_width=DEFAULT_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_VIEWPORT_HEIGHT,
        device_scale_factor=100 / 96.0,
        strict_pixels=False,
    )


def test_discover_cases_reuses_pdf_screenshot_inputs(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    _write_case(source, "01-basic")
    _write_case(source, "02-disabled", meta="html_enabled: false\n")
    (source / "_artifacts").mkdir()
    (source / "_artifacts" / "case.md").write_text("# ignored\n", encoding="utf-8")
    (source / ".hidden").mkdir()
    (source / ".hidden" / "case.md").write_text("# ignored\n", encoding="utf-8")
    (source / "notes").mkdir()

    cases = discover_cases(source)

    assert [case.name for case in cases] == ["01-basic", "02-disabled"]
    assert cases[0].md_path == source / "01-basic" / "case.md"
    assert cases[0].config_path == source / "01-basic" / "config.yaml"
    assert cases[1].html_enabled is False


def test_meta_defaults_are_html_specific(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    case_name = sorted(BASIC_RENDERER_CASES)[0]
    _write_case(source, case_name)

    case = discover_cases(source)[0]

    assert case.html_enabled is True
    assert case.html_tolerance_pixels == DEFAULT_HTML_TOLERANCE_PIXELS
    assert case.html_dpi == DEFAULT_HTML_DPI
    assert case.viewport_width == DEFAULT_VIEWPORT_WIDTH
    assert case.viewport_height == DEFAULT_VIEWPORT_HEIGHT
    assert case.device_scale_factor == DEFAULT_HTML_DPI / 96.0
    assert case.strict_pixels is False


def test_non_basic_cases_are_disabled_by_default(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    _write_case(source, "06-tables-simple")

    case = discover_cases(source)[0]

    assert case.html_enabled is False


def test_meta_html_enabled_override_wins_for_non_basic_cases(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    _write_case(source, "04-lists", meta="html_enabled: true\n")

    case = discover_cases(source)[0]

    assert case.html_enabled is True


def test_meta_uses_pdf_fields_as_fallbacks(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    _write_case(
        source,
        "01-fallbacks",
        meta="tolerance_pixels: 123\ndpi: 144\n",
    )

    case = discover_cases(source)[0]

    assert case.html_tolerance_pixels == 123
    assert case.html_dpi == 144


def test_meta_html_overrides_win(tmp_path: Path) -> None:
    source = tmp_path / "screenshot"
    _write_case(
        source,
        "01-overrides",
        meta=(
            "tolerance_pixels: 123\n"
            "dpi: 144\n"
            "html_tolerance_pixels: 456\n"
            "html_dpi: 120\n"
            "html_viewport_width: 900\n"
            "html_viewport_height: 1300\n"
            "html_device_scale_factor: 2\n"
            "html_strict_pixels: true\n"
        ),
    )

    case = discover_cases(source)[0]

    assert case.html_tolerance_pixels == 456
    assert case.html_dpi == 120
    assert case.viewport_width == 900
    assert case.viewport_height == 1300
    assert case.device_scale_factor == 2.0
    assert case.strict_pixels is True


def test_strict_pixel_diff_env_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("MARKDOWN_GOST_HTML_STRICT_PIXELS", "1")

    assert strict_pixel_diff_enabled() is True


def test_prepare_artifact_dir_removes_only_stale_page_dirs(tmp_path: Path) -> None:
    root = tmp_path / "_artifacts"
    artifact_dir = root / "01-basic" / "html"
    (artifact_dir / "page_001").mkdir(parents=True)
    (artifact_dir / "page_001" / "old.png").write_bytes(b"old")
    (artifact_dir / "page_count_mismatch").mkdir()
    (artifact_dir / "page_count_mismatch" / "old.png").write_bytes(b"old")
    (artifact_dir / "canonical.pdf").write_bytes(b"%PDF")

    prepared = prepare_artifact_dir(root, "01-basic")

    assert prepared == artifact_dir
    assert not (artifact_dir / "page_001").exists()
    assert not (artifact_dir / "page_count_mismatch").exists()
    assert (artifact_dir / "canonical.pdf").exists()


def test_compare_page_sets_allows_drift_within_tolerance(tmp_path: Path) -> None:
    case = _case(tmp_path, tolerance=1)
    expected = Image.new("RGB", (2, 2), (255, 255, 255))
    actual = expected.copy()
    actual.putpixel((0, 0), (254, 255, 255))

    failure = compare_page_sets(case, [expected], [actual], tmp_path / "artifacts")

    assert failure is None


def test_compare_page_sets_saves_drift_artifacts(tmp_path: Path) -> None:
    case = _case(tmp_path, tolerance=0)
    expected = Image.new("RGB", (3, 3), (255, 255, 255))
    actual = Image.new("RGB", (3, 3), (0, 0, 0))
    artifact_dir = tmp_path / "artifacts"

    failure = compare_page_sets(case, [expected], [actual], artifact_dir)

    assert failure is not None
    assert "html_tolerance_pixels=0" in failure.summary
    assert is_critical_html_failure(failure) is False
    assert (artifact_dir / "page_001" / "expected_pdf.png").exists()
    assert (artifact_dir / "page_001" / "actual_html.png").exists()
    assert (artifact_dir / "page_001" / "diff.png").exists()


def test_compare_page_sets_reports_page_count_mismatch(tmp_path: Path) -> None:
    case_dir = tmp_path / "06-tables-simple"
    case_dir.mkdir()
    case = HtmlCaseInputs(
        case=_case_inputs(case_dir),
        html_enabled=True,
        html_tolerance_pixels=0,
        html_dpi=100,
        viewport_width=DEFAULT_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_VIEWPORT_HEIGHT,
        device_scale_factor=100 / 96.0,
        strict_pixels=False,
    )
    expected = [
        Image.new("RGB", (2, 2), (255, 255, 255)),
        Image.new("RGB", (2, 2), (250, 250, 250)),
    ]
    actual = [Image.new("RGB", (2, 2), (255, 255, 255))]
    artifact_dir = tmp_path / "artifacts"

    failure = compare_page_sets(case, expected, actual, artifact_dir)

    assert failure is not None
    assert "category=table/listing" in failure.summary
    assert "expected_pdf=2 actual_html=1" in failure.summary
    assert is_critical_html_failure(failure) is True
    assert (artifact_dir / "page_count_mismatch" / "expected_pdf_001.png").exists()
    assert (artifact_dir / "page_count_mismatch" / "expected_pdf_002.png").exists()
    assert (artifact_dir / "page_count_mismatch" / "actual_html_001.png").exists()


def test_html_metric_ignores_one_pixel_antialias_displacement() -> None:
    expected = Image.new("RGB", (8, 8), (255, 255, 255))
    actual = expected.copy()
    expected.putpixel((2, 2), (0, 0, 0))
    actual.putpixel((3, 2), (0, 0, 0))

    first = measure_html_page(expected, actual, index=0)
    second = measure_html_page(expected, actual, index=0)

    assert first.raw_differing_pixels == 2
    assert first.differing_pixels == 0
    assert first.compared_pixels == 64
    assert first.differing_rate == 0.0
    assert first.to_dict() == second.to_dict()


def test_locator_screenshot_normalization_removes_position_rounding_pixel() -> None:
    screenshot = Image.new("RGB", (827, 1171), (240, 240, 240))
    screenshot.putpixel((0, 0), (10, 20, 30))

    normalized = _normalize_locator_screenshot(
        screenshot,
        css_size=(793.6875, 1122.515625),
        device_scale_factor=100 / 96.0,
    )

    assert normalized.size == (827, 1170)
    assert normalized.getpixel((0, 0)) == (10, 20, 30)


def test_html_metric_detects_material_geometry_shift_and_records_sizes() -> None:
    expected = Image.new("RGB", (8, 8), (255, 255, 255))
    actual = Image.new("RGB", (10, 8), (255, 255, 255))
    expected.putpixel((1, 2), (0, 0, 0))
    actual.putpixel((8, 2), (0, 0, 0))

    measurement = measure_html_page(expected, actual, index=2)

    assert measurement.index == 2
    assert measurement.expected_size == (8, 8)
    assert measurement.actual_size == (10, 8)
    assert measurement.differing_pixels == 3
    assert measurement.compared_pixels == 64
    assert measurement.differing_rate == 3 / 64


def test_calibration_summary_is_weighted_and_reports_page_count_mismatch() -> None:
    expected = Image.new("RGB", (4, 4), (255, 255, 255))
    actual = expected.copy()
    expected.putpixel((0, 0), (0, 0, 0))
    actual.putpixel((3, 3), (0, 0, 0))
    measured = measure_html_page(expected, actual, index=0)
    matched = HtmlCaseMetrics(
        case="matched",
        expected_pages=1,
        actual_pages=1,
        pages=(measured,),
    )
    mismatched = HtmlCaseMetrics(
        case="mismatched",
        expected_pages=2,
        actual_pages=1,
        pages=(),
    )

    summary = build_calibration_summary([matched, mismatched])

    assert summary["aggregate"]["expected_pages"] == 3
    assert summary["aggregate"]["actual_pages"] == 2
    assert summary["aggregate"]["page_count_mismatches"] == 1
    assert summary["aggregate"]["differing_pixels"] == 2
    assert summary["aggregate"]["compared_pixels"] == 16
    assert summary["aggregate"]["differing_rate"] == 0.125
    assert summary["aggregate"]["worst_case_rate"] == 0.125


def test_calibrate_page_sets_preserves_all_artifacts_on_count_mismatch(
    tmp_path: Path,
) -> None:
    expected = [
        Image.new("RGB", (4, 4), (255, 255, 255)),
        Image.new("RGB", (4, 4), (240, 240, 240)),
    ]
    actual = [Image.new("RGB", (4, 4), (0, 0, 0))]

    metrics = calibrate_page_sets(
        "count-mismatch",
        expected,
        actual,
        tmp_path,
    )

    assert metrics.page_count_mismatch is True
    assert len(metrics.pages) == 1
    assert (tmp_path / "expected" / "expected_pdf_001.png").exists()
    assert (tmp_path / "expected" / "expected_pdf_002.png").exists()
    assert (tmp_path / "actual" / "actual_html_001.png").exists()
    assert (tmp_path / "page_001" / "expected_pdf.png").exists()
    assert (tmp_path / "page_001" / "actual_html.png").exists()
    assert (tmp_path / "page_001" / "diff.png").exists()
    assert (tmp_path / "page_001" / "raw_diff.png").exists()


def test_regression_policy_allows_improvement_and_flags_material_worsening() -> None:
    reference = {
        "thresholds": {
            "aggregate_relative": 0.10,
            "aggregate_absolute": 0.001,
            "case_relative": 0.15,
            "case_absolute": 0.001,
            "worst_page_relative": 0.10,
            "worst_page_absolute": 0.001,
        },
        "aggregate": {
            "differing_rate": 0.02,
            "worst_page_rate": 0.03,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 1,
                "differing_rate": 0.02,
            }
        ],
    }
    improved = {
        "aggregate": {
            "differing_rate": 0.015,
            "worst_page_rate": 0.02,
            "page_count_mismatches": 0,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 1,
                "actual_pages": 1,
                "differing_rate": 0.015,
            }
        ],
    }
    worsened = {
        "aggregate": {
            "differing_rate": 0.04,
            "worst_page_rate": 0.05,
            "page_count_mismatches": 0,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 1,
                "actual_pages": 1,
                "differing_rate": 0.04,
            }
        ],
    }

    assert regression_failures(improved, reference) == []
    failures = regression_failures(worsened, reference)
    assert any("aggregate differing_rate" in failure for failure in failures)
    assert any("worst_page_rate" in failure for failure in failures)
    assert any("one differing_rate" in failure for failure in failures)


def test_regression_policy_rejects_lost_coverage_and_page_count_drift() -> None:
    reference = {
        "thresholds": {},
        "aggregate": {"differing_rate": 0.0, "worst_page_rate": 0.0},
        "cases": [
            {"case": "one", "expected_pages": 2, "differing_rate": 0.0},
            {"case": "missing", "expected_pages": 1, "differing_rate": 0.0},
        ],
    }
    actual = {
        "aggregate": {
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
            "page_count_mismatches": 1,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 2,
                "actual_pages": 1,
                "differing_rate": 0.0,
            }
        ],
    }

    failures = regression_failures(actual, reference)

    assert any("page-count mismatch" in failure for failure in failures)
    assert any("missing calibrated case: missing" in failure for failure in failures)


def test_regression_policy_rejects_metric_definition_changes() -> None:
    reference = {
        "metric": {
            "ink_luminance_threshold": 245,
            "antialias_tolerance_radius_px": 1,
        },
        "thresholds": {},
        "aggregate": {"differing_rate": 0.1, "worst_page_rate": 0.1},
        "cases": [],
    }
    actual = {
        "metric": {
            "ink_luminance_threshold": 0,
            "antialias_tolerance_radius_px": 20,
        },
        "aggregate": {
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
            "page_count_mismatches": 0,
        },
        "cases": [],
    }

    failures = regression_failures(actual, reference)

    assert any("ink_luminance_threshold" in failure for failure in failures)
    assert any("antialias_tolerance_radius_px" in failure for failure in failures)


def test_regression_policy_rejects_schema_version_changes() -> None:
    reference = {
        "schema_version": 1,
        "metric": {},
        "thresholds": {},
        "aggregate": {"differing_rate": 0.0, "worst_page_rate": 0.0},
        "cases": [],
    }
    actual = {
        "schema_version": 2,
        "metric": {},
        "aggregate": {
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
            "page_count_mismatches": 0,
        },
        "cases": [],
    }

    failures = regression_failures(actual, reference)

    assert any("schema_version" in failure for failure in failures)


def test_regression_policy_rejects_localized_page_regression() -> None:
    reference = {
        "schema_version": 1,
        "metric": {},
        "thresholds": {"page_relative": 0.0, "page_absolute": 0.0},
        "aggregate": {"differing_rate": 0.01, "worst_page_rate": 0.03},
        "cases": [
            {
                "case": "one",
                "expected_pages": 2,
                "differing_rate": 0.01,
                "pages": [
                    {"page": 1, "differing_rate": 0.001},
                    {"page": 2, "differing_rate": 0.019},
                ],
            }
        ],
    }
    actual = {
        "schema_version": 1,
        "metric": {},
        "aggregate": {
            "differing_rate": 0.01,
            "worst_page_rate": 0.025,
            "page_count_mismatches": 0,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 2,
                "actual_pages": 2,
                "differing_rate": 0.01,
                "pages": [
                    {"page": 1, "differing_rate": 0.025},
                    {"page": 2, "differing_rate": 0.0},
                ],
            }
        ],
    }

    failures = regression_failures(actual, reference)

    assert any("one page 1 differing_rate" in failure for failure in failures)


def test_regression_policy_rejects_raw_visual_regression() -> None:
    reference = {
        "metric": {},
        "thresholds": {
            "raw_aggregate_relative": 0.0,
            "raw_aggregate_absolute": 0.0,
        },
        "aggregate": {
            "raw_differing_pixels": 10,
            "compared_pixels": 100,
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
        },
        "cases": [],
    }
    actual = {
        "metric": {},
        "aggregate": {
            "raw_differing_pixels": 11,
            "compared_pixels": 100,
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
            "page_count_mismatches": 0,
        },
        "cases": [],
    }

    failures = regression_failures(actual, reference)

    assert any("raw_differing_rate" in failure for failure in failures)


def test_regression_policy_rejects_page_image_dimension_drift() -> None:
    reference = {
        "thresholds": {},
        "aggregate": {"differing_rate": 0.0, "worst_page_rate": 0.0},
        "cases": [
            {"case": "one", "expected_pages": 1, "differing_rate": 0.0},
        ],
    }
    actual = {
        "aggregate": {
            "differing_rate": 0.0,
            "worst_page_rate": 0.0,
            "page_count_mismatches": 0,
        },
        "cases": [
            {
                "case": "one",
                "expected_pages": 1,
                "actual_pages": 1,
                "differing_rate": 0.0,
                "pages": [
                    {
                        "page": 1,
                        "expected_size": [827, 1170],
                        "actual_size": [826, 1170],
                    }
                ],
            }
        ],
    }

    failures = regression_failures(actual, reference)

    assert failures == ["one page 1 image-size mismatch: expected=827x1170 actual=826x1170"]


def test_renderer_detection_reports_preview_renderer_available() -> None:
    availability = detect_html_renderer()

    assert availability.available is True
    assert "importable" in availability.reason


def test_render_html_case_writes_preview_html(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path, "01-basic")
    case = HtmlCaseInputs(
        case=_case_inputs(case_dir),
        html_enabled=True,
        html_tolerance_pixels=DEFAULT_HTML_TOLERANCE_PIXELS,
        html_dpi=DEFAULT_HTML_DPI,
        viewport_width=DEFAULT_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_VIEWPORT_HEIGHT,
        device_scale_factor=DEFAULT_HTML_DPI / 96.0,
        strict_pixels=False,
    )
    out_html = tmp_path / "actual.html"

    render_html_case(case, out_html)

    rendered = out_html.read_text(encoding="utf-8")
    assert rendered.startswith("<!doctype html>")
    assert 'data-md2gost-page="1"' in rendered
    assert "<h1" in rendered


def test_render_html_case_resolves_local_image_assets(tmp_path: Path) -> None:
    case_dir = _write_case(tmp_path, "05-images")
    Image.new("RGB", (24, 12), (30, 80, 120)).save(case_dir / "pic.png")
    (case_dir / "case.md").write_text("![Pic](pic.png)\n", encoding="utf-8")
    case = HtmlCaseInputs(
        case=_case_inputs(case_dir),
        html_enabled=True,
        html_tolerance_pixels=DEFAULT_HTML_TOLERANCE_PIXELS,
        html_dpi=DEFAULT_HTML_DPI,
        viewport_width=DEFAULT_VIEWPORT_WIDTH,
        viewport_height=DEFAULT_VIEWPORT_HEIGHT,
        device_scale_factor=DEFAULT_HTML_DPI / 96.0,
        strict_pixels=False,
    )
    out_html = tmp_path / "actual.html"

    render_html_case(case, out_html)

    rendered = out_html.read_text(encoding="utf-8")
    assert f'src="{(case_dir / "pic.png").resolve().as_uri()}"' in rendered
    assert "data:image" not in rendered
    assert "base64" not in rendered.lower()
    assert "aspect-ratio: 24 / 12;" in rendered
