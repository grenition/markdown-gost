"""HTML screenshot parity pipeline."""

from __future__ import annotations

import importlib.util
import math
import os
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from _diff import diff_pages
from _pipeline import CaseFailure, CaseInputs, PageDiff
from PIL import Image, ImageChops, ImageFilter

DEFAULT_HTML_TOLERANCE_PIXELS = 500
DEFAULT_HTML_DPI = 100
DEFAULT_VIEWPORT_WIDTH = 794
DEFAULT_VIEWPORT_HEIGHT = 1123
HTML_RUNTIME_STRICT_ENV = "MARKDOWN_GOST_HTML_STRICT_RUNTIME"
HTML_STRICT_PIXELS_ENV = "MARKDOWN_GOST_HTML_STRICT_PIXELS"
HTML_INK_LUMINANCE_THRESHOLD = 245
HTML_ANTIALIAS_TOLERANCE_RADIUS_PX = 1
DEFAULT_AGGREGATE_REGRESSION_RELATIVE = 0.10
DEFAULT_AGGREGATE_REGRESSION_ABSOLUTE = 0.0001
DEFAULT_CASE_REGRESSION_RELATIVE = 0.15
DEFAULT_CASE_REGRESSION_ABSOLUTE = 0.0003
DEFAULT_PAGE_REGRESSION_RELATIVE = 0.15
DEFAULT_PAGE_REGRESSION_ABSOLUTE = 0.0003
DEFAULT_WORST_PAGE_REGRESSION_RELATIVE = 0.10
DEFAULT_WORST_PAGE_REGRESSION_ABSOLUTE = 0.0002
BASIC_RENDERER_CASES = frozenset(
    {
        "01-basic-paragraphs",
        "01a-config-paragraph",
        "02-headings",
        "02a-config-headings",
        "03-page-break",
        "03a-config-page",
        "04-lists",
        "05-images",
        "05b-images-sized",
        "05c-config-caption-image",
    }
)

PAGE_SELECTORS = (
    "[data-md2gost-page]",
    ".md2gost-page",
    ".page",
)

DISABLE_ANIMATIONS_CSS = """
*, *::before, *::after {
  animation-delay: 0s !important;
  animation-duration: 0s !important;
  animation-iteration-count: 1 !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
  transition-delay: 0s !important;
  transition-duration: 0s !important;
}
html, body {
  background: #fff !important;
}
.md2gost-preview {
  background: #fff !important;
  gap: 0 !important;
  padding: 0 !important;
}
.md2gost-page {
  box-shadow: none !important;
}
"""


class HarnessError(RuntimeError):
    """Pipeline error that should fail a test with a clear message."""


@dataclass(frozen=True)
class RuntimeAvailability:
    available: bool
    reason: str


@dataclass(frozen=True)
class HtmlCaseInputs:
    """A discovered HTML parity case backed by tests/screenshot/<case>."""

    case: CaseInputs
    html_enabled: bool
    html_tolerance_pixels: int
    html_dpi: int
    viewport_width: int
    viewport_height: int
    device_scale_factor: float
    strict_pixels: bool

    @property
    def name(self) -> str:
        return self.case.name

    @property
    def source_case_dir(self) -> Path:
        return self.case.case_dir

    @property
    def md_path(self) -> Path:
        return self.case.md_path

    @property
    def config_path(self) -> Path:
        return self.case.config_path


@dataclass(frozen=True)
class HtmlPageMeasurement:
    """Deterministic raw and raster-tolerant metrics for one page pair."""

    index: int
    expected_size: tuple[int, int]
    actual_size: tuple[int, int]
    raw_differing_pixels: int
    differing_pixels: int
    compared_pixels: int
    expected: Image.Image
    actual: Image.Image
    overlay: Image.Image

    @property
    def differing_rate(self) -> float:
        if self.compared_pixels == 0:
            return 0.0
        return self.differing_pixels / self.compared_pixels

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.index + 1,
            "expected_size": list(self.expected_size),
            "actual_size": list(self.actual_size),
            "raw_differing_pixels": self.raw_differing_pixels,
            "differing_pixels": self.differing_pixels,
            "compared_pixels": self.compared_pixels,
            "differing_rate": round(self.differing_rate, 8),
        }


@dataclass(frozen=True)
class HtmlCaseMetrics:
    """Quantitative HTML/PDF parity result for one canonical case."""

    case: str
    expected_pages: int
    actual_pages: int
    pages: tuple[HtmlPageMeasurement, ...]

    @property
    def page_count_mismatch(self) -> bool:
        return self.expected_pages != self.actual_pages

    @property
    def raw_differing_pixels(self) -> int:
        return sum(page.raw_differing_pixels for page in self.pages)

    @property
    def differing_pixels(self) -> int:
        return sum(page.differing_pixels for page in self.pages)

    @property
    def compared_pixels(self) -> int:
        return sum(page.compared_pixels for page in self.pages)

    @property
    def differing_rate(self) -> float:
        if self.compared_pixels == 0:
            return 0.0
        return self.differing_pixels / self.compared_pixels

    @property
    def worst_page_rate(self) -> float:
        return max((page.differing_rate for page in self.pages), default=0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "expected_pages": self.expected_pages,
            "actual_pages": self.actual_pages,
            "page_count_mismatch": self.page_count_mismatch,
            "raw_differing_pixels": self.raw_differing_pixels,
            "differing_pixels": self.differing_pixels,
            "compared_pixels": self.compared_pixels,
            "differing_rate": round(self.differing_rate, 8),
            "worst_page_rate": round(self.worst_page_rate, 8),
            "pages": [page.to_dict() for page in self.pages],
        }


def discover_cases(screenshot_root: Path) -> list[HtmlCaseInputs]:
    """Find HTML parity cases from the canonical PDF screenshot case tree."""
    cases: list[HtmlCaseInputs] = []
    for child in sorted(screenshot_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in {"__pycache__", "_artifacts"}:
            continue
        if child.name.startswith("."):
            continue
        if not (child / "case.md").exists():
            continue
        cases.append(_load_case(child))
    return cases


def _load_case(case_dir: Path) -> HtmlCaseInputs:
    md_path = case_dir / "case.md"
    config_path = case_dir / "config.yaml"

    if not config_path.exists():
        raise HarnessError(f"{case_dir.name}: missing config.yaml")

    meta = _read_meta(case_dir / "meta.yaml")
    base_tolerance = int(meta.get("tolerance_pixels", DEFAULT_HTML_TOLERANCE_PIXELS))
    base_dpi = int(meta.get("dpi", DEFAULT_HTML_DPI))

    case = CaseInputs(
        name=case_dir.name,
        case_dir=case_dir,
        md_path=md_path,
        config_path=config_path,
        expected_pdf=case_dir / "expected.pdf",
        tolerance_pixels=base_tolerance,
        dpi=base_dpi,
    )
    return html_case_from_screenshot_case(case)


def html_case_from_screenshot_case(case: CaseInputs) -> HtmlCaseInputs:
    meta = _read_meta(case.case_dir / "meta.yaml")
    base_tolerance = int(meta.get("tolerance_pixels", case.tolerance_pixels))
    base_dpi = int(meta.get("dpi", case.dpi))
    html_dpi = int(meta.get("html_dpi", base_dpi))
    return HtmlCaseInputs(
        case=case,
        html_enabled=_as_bool(
            meta.get("html_enabled"),
            default=case.name in BASIC_RENDERER_CASES,
        ),
        html_tolerance_pixels=int(meta.get("html_tolerance_pixels", base_tolerance)),
        html_dpi=html_dpi,
        viewport_width=int(meta.get("html_viewport_width", DEFAULT_VIEWPORT_WIDTH)),
        viewport_height=int(meta.get("html_viewport_height", DEFAULT_VIEWPORT_HEIGHT)),
        device_scale_factor=float(meta.get("html_device_scale_factor", html_dpi / 96.0)),
        strict_pixels=_as_bool(
            meta.get("html_strict_pixels"),
            default=strict_pixel_diff_enabled(),
        ),
    )


def _read_meta(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HarnessError(f"{meta_path}: expected mapping")
    return data


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def strict_runtime_enabled() -> bool:
    return os.environ.get(HTML_RUNTIME_STRICT_ENV, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def strict_pixel_diff_enabled() -> bool:
    return os.environ.get(HTML_STRICT_PIXELS_ENV, "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_critical_html_failure(failure: CaseFailure) -> bool:
    """Critical HTML parity failures should fail even in report-only pixel mode."""
    return not failure.pages


def detect_html_renderer() -> RuntimeAvailability:
    try:
        from markdown_gost.preview import build_preview_model, render_preview_html
    except ImportError as exc:
        return RuntimeAvailability(
            available=False,
            reason=f"HTML renderer import failed: {exc}",
        )
    if not callable(build_preview_model) or not callable(render_preview_html):
        return RuntimeAvailability(
            available=False,
            reason="HTML renderer entrypoints are not callable",
        )
    return RuntimeAvailability(available=True, reason="HTML renderer is importable")


def detect_headless_browser() -> RuntimeAvailability:
    if importlib.util.find_spec("playwright") is None:
        return RuntimeAvailability(
            available=False,
            reason="Playwright is not installed, so no headless browser is available",
        )
    return RuntimeAvailability(available=True, reason="Playwright is importable")


def detect_html_runtime() -> RuntimeAvailability:
    renderer = detect_html_renderer()
    if not renderer.available:
        return renderer
    browser = detect_headless_browser()
    if not browser.available:
        return browser
    return RuntimeAvailability(available=True, reason="HTML runtime is available")


def render_html_case(case: HtmlCaseInputs, out_html: Path) -> None:
    """Render a case through the preview model HTML renderer."""
    from markdown_gost.config.loader import load_config_from_path
    from markdown_gost.preview import build_preview_model, render_preview_html
    from markdown_gost.storage import FilesystemStorage

    markdown = case.md_path.read_text(encoding="utf-8")
    config = load_config_from_path(case.config_path)
    model = build_preview_model(
        markdown,
        config,
        FilesystemStorage(base_dir=case.source_case_dir),
    )
    out_html.write_text(
        render_preview_html(
            model,
            asset_resolver=_local_asset_resolver(case),
        ),
        encoding="utf-8",
    )


def _local_asset_resolver(case: HtmlCaseInputs):
    case_root = case.source_case_dir.resolve()

    def resolve(asset_path: str) -> str:
        candidate = (case_root / asset_path).resolve()
        try:
            candidate.relative_to(case_root)
        except ValueError:
            return f"/api/preview/assets/{quote(asset_path, safe='')}"
        if not candidate.is_file():
            return f"/api/preview/assets/{quote(asset_path, safe='')}"
        return candidate.as_uri()

    return resolve


def capture_html_pages(html_path: Path, case: HtmlCaseInputs) -> list[Image.Image]:
    """Capture HTML pages with Playwright when the optional runtime exists."""
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime gate covers this
        raise HarnessError("Playwright is not installed") from exc

    images: list[Image.Image] = []
    selector = ", ".join(PAGE_SELECTORS)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={
                    "width": case.viewport_width,
                    "height": case.viewport_height,
                },
                device_scale_factor=case.device_scale_factor,
            )
            page = context.new_page()
            page.emulate_media(media="screen", reduced_motion="reduce")
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.add_style_tag(content=DISABLE_ANIMATIONS_CSS)

            pages = page.locator(selector)
            count = pages.count()
            if count:
                for i in range(count):
                    page_locator = pages.nth(i)
                    original_style = page_locator.evaluate(
                        """element => {
                            const original = element.style.cssText;
                            element.style.setProperty('position', 'fixed', 'important');
                            element.style.setProperty('inset', '0 auto auto 0', 'important');
                            element.style.setProperty('margin', '0', 'important');
                            element.style.setProperty('z-index', '2147483647', 'important');
                            return original;
                        }"""
                    )
                    try:
                        if page_locator.locator("img").count():
                            page_locator.evaluate(
                                """async root => {
                            const images = Array.from(root.querySelectorAll('img'));
                            await Promise.all(images.map(async image => {
                                if (!image.complete) {
                                    await new Promise(resolve => {
                                        image.addEventListener('load', resolve, {once: true});
                                        image.addEventListener('error', resolve, {once: true});
                                    });
                                }
                                if (image.decode) {
                                    await image.decode().catch(() => {});
                                }
                            }));
                        }"""
                            )
                        box = page_locator.bounding_box()
                        raw = page_locator.screenshot(type="png", animations="disabled")
                        image = Image.open(BytesIO(raw)).convert("RGB")
                        if box is not None:
                            image = _normalize_locator_screenshot(
                                image,
                                css_size=(box["width"], box["height"]),
                                device_scale_factor=case.device_scale_factor,
                            )
                        images.append(image)
                    finally:
                        page_locator.evaluate(
                            "(element, original) => { element.style.cssText = original; }",
                            original_style,
                        )
            else:
                raw = page.screenshot(
                    full_page=True,
                    type="png",
                    animations="disabled",
                )
                images.append(Image.open(BytesIO(raw)).convert("RGB"))
        finally:
            browser.close()
    return images


def _normalize_locator_screenshot(
    image: Image.Image,
    *,
    css_size: tuple[float, float],
    device_scale_factor: float,
) -> Image.Image:
    """Remove Playwright's position-dependent extra trailing edge pixel.

    Locator screenshots round the element's absolute fractional coordinates to
    device pixels. Identical pages can therefore alternate between N and N+1
    pixels by vertical position. The CSS dimensions themselves have a stable
    device-pixel ceiling, so only the right/bottom edges are cropped or padded.
    """

    target = (
        max(1, math.ceil(css_size[0] * device_scale_factor)),
        max(1, math.ceil(css_size[1] * device_scale_factor)),
    )
    source = image.convert("RGB")
    normalized = Image.new("RGB", target, (255, 255, 255))
    normalized.paste(
        source.crop((0, 0, min(source.width, target[0]), min(source.height, target[1])))
    )
    return normalized


def prepare_artifact_dir(root: Path, case_name: str) -> Path:
    """Create a per-case artifact dir and remove stale page diff subdirs."""
    target = root / case_name / "html"
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir() and (
            child.name == "page_count_mismatch" or child.name.startswith("page_")
        ):
            shutil.rmtree(child)
    return target


def measure_html_page(
    expected: Image.Image,
    actual: Image.Image,
    *,
    index: int,
    ink_luminance_threshold: int = HTML_INK_LUMINANCE_THRESHOLD,
    antialias_tolerance_radius_px: int = HTML_ANTIALIAS_TOLERANCE_RADIUS_PX,
) -> HtmlPageMeasurement:
    """Measure page drift while tolerating one-pixel rasterization differences.

    The raw metric retains the exact RGB comparison used by the historical
    screenshot gate. The layout metric binarizes visible ink and discounts ink
    found within a small neighbourhood in the other renderer. This keeps text
    antialiasing differences from dominating while still detecting displaced
    glyphs, borders, images, and whole blocks.
    """

    if not 0 <= ink_luminance_threshold <= 255:
        raise ValueError("ink_luminance_threshold must be in 0..255")
    if antialias_tolerance_radius_px < 0:
        raise ValueError("antialias_tolerance_radius_px must be non-negative")

    expected_rgb = expected.convert("RGB")
    actual_rgb = actual.convert("RGB")
    actual_size = actual_rgb.size
    if actual_rgb.size != expected_rgb.size:
        actual_rgb = actual_rgb.resize(expected_rgb.size)

    raw_diff = ImageChops.difference(expected_rgb, actual_rgb)
    raw_mask = raw_diff.convert("L").point(lambda value: 255 if value > 0 else 0)
    raw_differing_pixels = raw_mask.histogram()[255]

    expected_ink = _ink_mask(expected_rgb, ink_luminance_threshold)
    actual_ink = _ink_mask(actual_rgb, ink_luminance_threshold)
    expected_near = _expanded_mask(
        expected_ink,
        antialias_tolerance_radius_px,
    )
    actual_near = _expanded_mask(
        actual_ink,
        antialias_tolerance_radius_px,
    )
    unmatched_expected = ImageChops.multiply(
        expected_ink,
        ImageChops.invert(actual_near),
    )
    unmatched_actual = ImageChops.multiply(
        actual_ink,
        ImageChops.invert(expected_near),
    )
    unmatched = ImageChops.lighter(unmatched_expected, unmatched_actual)
    differing_pixels = unmatched.histogram()[255]

    overlay = expected_rgb.copy()
    overlay.paste(
        Image.new("RGB", expected_rgb.size, (255, 0, 0)),
        mask=unmatched,
    )
    return HtmlPageMeasurement(
        index=index,
        expected_size=expected_rgb.size,
        actual_size=actual_size,
        raw_differing_pixels=raw_differing_pixels,
        differing_pixels=differing_pixels,
        compared_pixels=expected_rgb.width * expected_rgb.height,
        expected=expected_rgb,
        actual=actual_rgb,
        overlay=overlay,
    )


def calibrate_page_sets(
    case_name: str,
    expected_pdf_pages: list[Image.Image],
    actual_html_pages: list[Image.Image],
    artifact_dir: Path,
) -> HtmlCaseMetrics:
    """Measure every comparable page and retain artifacts even on success."""

    expected_dir = artifact_dir / "expected"
    actual_dir = artifact_dir / "actual"
    expected_dir.mkdir(parents=True, exist_ok=True)
    actual_dir.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(expected_pdf_pages, 1):
        image.convert("RGB").save(expected_dir / f"expected_pdf_{index:03d}.png")
    for index, image in enumerate(actual_html_pages, 1):
        image.convert("RGB").save(actual_dir / f"actual_html_{index:03d}.png")

    measurements: list[HtmlPageMeasurement] = []
    for index, (expected, actual) in enumerate(
        zip(expected_pdf_pages, actual_html_pages, strict=False)
    ):
        measurement = measure_html_page(expected, actual, index=index)
        page_dir = artifact_dir / f"page_{index + 1:03d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        measurement.expected.save(page_dir / "expected_pdf.png")
        measurement.actual.save(page_dir / "actual_html.png")
        measurement.overlay.save(page_dir / "diff.png")
        diff_pages(expected, actual).overlay.save(page_dir / "raw_diff.png")
        measurements.append(measurement)

    return HtmlCaseMetrics(
        case=case_name,
        expected_pages=len(expected_pdf_pages),
        actual_pages=len(actual_html_pages),
        pages=tuple(measurements),
    )


def _ink_mask(image: Image.Image, threshold: int) -> Image.Image:
    return image.convert("L").point(lambda value: 255 if value < threshold else 0)


def _expanded_mask(mask: Image.Image, radius: int) -> Image.Image:
    if radius == 0:
        return mask
    return mask.filter(ImageFilter.MaxFilter(radius * 2 + 1))


def build_calibration_summary(
    cases: list[HtmlCaseMetrics],
) -> dict[str, Any]:
    """Build a stable weighted summary for a complete calibration run."""

    ordered_cases = sorted(cases, key=lambda item: item.case)
    expected_pages = sum(case.expected_pages for case in ordered_cases)
    actual_pages = sum(case.actual_pages for case in ordered_cases)
    raw_differing_pixels = sum(case.raw_differing_pixels for case in ordered_cases)
    differing_pixels = sum(case.differing_pixels for case in ordered_cases)
    compared_pixels = sum(case.compared_pixels for case in ordered_cases)
    differing_rate = differing_pixels / compared_pixels if compared_pixels else 0.0
    return {
        "schema_version": 1,
        "metric": {
            "ink_luminance_threshold": HTML_INK_LUMINANCE_THRESHOLD,
            "antialias_tolerance_radius_px": (HTML_ANTIALIAS_TOLERANCE_RADIUS_PX),
        },
        "aggregate": {
            "expected_pages": expected_pages,
            "actual_pages": actual_pages,
            "page_count_mismatches": sum(1 for case in ordered_cases if case.page_count_mismatch),
            "raw_differing_pixels": raw_differing_pixels,
            "differing_pixels": differing_pixels,
            "compared_pixels": compared_pixels,
            "differing_rate": round(differing_rate, 8),
            "worst_case_rate": round(
                max(
                    (case.differing_rate for case in ordered_cases),
                    default=0.0,
                ),
                8,
            ),
            "worst_page_rate": round(
                max(
                    (case.worst_page_rate for case in ordered_cases),
                    default=0.0,
                ),
                8,
            ),
        },
        "cases": [case.to_dict() for case in ordered_cases],
    }


def regression_failures(
    actual: dict[str, Any],
    reference: dict[str, Any],
) -> list[str]:
    """Return deterministic calibration regressions against a reviewed reference."""

    failures: list[str] = []
    if actual.get("schema_version") != reference.get("schema_version"):
        failures.append(
            "calibration schema_version changed: "
            f"reference={reference.get('schema_version')!r} "
            f"actual={actual.get('schema_version')!r}"
        )
    actual_metric = actual.get("metric") or {}
    reference_metric = reference.get("metric") or {}
    for key in ("ink_luminance_threshold", "antialias_tolerance_radius_px"):
        if actual_metric.get(key) != reference_metric.get(key):
            failures.append(
                f"calibration metric changed: {key} "
                f"reference={reference_metric.get(key)!r} actual={actual_metric.get(key)!r}"
            )
    thresholds = reference.get("thresholds") or {}
    aggregate_relative = float(
        thresholds.get(
            "aggregate_relative",
            DEFAULT_AGGREGATE_REGRESSION_RELATIVE,
        )
    )
    aggregate_absolute = float(
        thresholds.get(
            "aggregate_absolute",
            DEFAULT_AGGREGATE_REGRESSION_ABSOLUTE,
        )
    )
    case_relative = float(thresholds.get("case_relative", DEFAULT_CASE_REGRESSION_RELATIVE))
    case_absolute = float(thresholds.get("case_absolute", DEFAULT_CASE_REGRESSION_ABSOLUTE))
    page_relative = float(thresholds.get("page_relative", DEFAULT_PAGE_REGRESSION_RELATIVE))
    page_absolute = float(thresholds.get("page_absolute", DEFAULT_PAGE_REGRESSION_ABSOLUTE))
    raw_aggregate_relative = float(thresholds.get("raw_aggregate_relative", 0.05))
    raw_aggregate_absolute = float(thresholds.get("raw_aggregate_absolute", 0.001))
    worst_page_relative = float(
        thresholds.get(
            "worst_page_relative",
            DEFAULT_WORST_PAGE_REGRESSION_RELATIVE,
        )
    )
    worst_page_absolute = float(
        thresholds.get(
            "worst_page_absolute",
            DEFAULT_WORST_PAGE_REGRESSION_ABSOLUTE,
        )
    )

    actual_aggregate = actual.get("aggregate") or {}
    reference_aggregate = reference.get("aggregate") or {}
    if int(actual_aggregate.get("page_count_mismatches", 0)):
        failures.append(
            "calibration has page-count mismatch(es): "
            f"{actual_aggregate.get('page_count_mismatches')}"
        )

    _append_rate_regression(
        failures,
        label="aggregate differing_rate",
        actual=float(actual_aggregate.get("differing_rate", 0.0)),
        reference=float(reference_aggregate.get("differing_rate", 0.0)),
        relative=aggregate_relative,
        absolute=aggregate_absolute,
    )
    actual_compared = max(1, int(actual_aggregate.get("compared_pixels", 0)))
    reference_compared = max(1, int(reference_aggregate.get("compared_pixels", 0)))
    _append_rate_regression(
        failures,
        label="aggregate raw_differing_rate",
        actual=float(actual_aggregate.get("raw_differing_pixels", 0)) / actual_compared,
        reference=(float(reference_aggregate.get("raw_differing_pixels", 0)) / reference_compared),
        relative=raw_aggregate_relative,
        absolute=raw_aggregate_absolute,
    )
    _append_rate_regression(
        failures,
        label="worst_page_rate",
        actual=float(actual_aggregate.get("worst_page_rate", 0.0)),
        reference=float(reference_aggregate.get("worst_page_rate", 0.0)),
        relative=worst_page_relative,
        absolute=worst_page_absolute,
    )

    actual_cases = {str(case["case"]): case for case in actual.get("cases") or []}
    reference_cases = {str(case["case"]): case for case in reference.get("cases") or []}
    for case_name in sorted(reference_cases.keys() - actual_cases.keys()):
        failures.append(f"missing calibrated case: {case_name}")
    for case_name in sorted(actual_cases.keys() - reference_cases.keys()):
        failures.append(f"unreviewed calibrated case: {case_name}")

    for case_name in sorted(reference_cases.keys() & actual_cases.keys()):
        actual_case = actual_cases[case_name]
        reference_case = reference_cases[case_name]
        expected_pages = int(reference_case.get("expected_pages", 0))
        current_expected = int(actual_case.get("expected_pages", 0))
        current_actual = int(actual_case.get("actual_pages", 0))
        if current_expected != expected_pages:
            failures.append(
                f"{case_name} oracle page count changed: "
                f"reference={expected_pages} current={current_expected}"
            )
        if current_actual != current_expected:
            failures.append(
                f"{case_name} page-count mismatch: "
                f"expected={current_expected} actual={current_actual}"
            )
        for page in actual_case.get("pages") or []:
            expected_size = page.get("expected_size") or []
            actual_size = page.get("actual_size") or []
            if expected_size == actual_size or len(expected_size) != 2 or len(actual_size) != 2:
                continue
            failures.append(
                f"{case_name} page {page.get('page')} image-size mismatch: "
                f"expected={expected_size[0]}x{expected_size[1]} "
                f"actual={actual_size[0]}x{actual_size[1]}"
            )
        _append_rate_regression(
            failures,
            label=f"{case_name} differing_rate",
            actual=float(actual_case.get("differing_rate", 0.0)),
            reference=float(reference_case.get("differing_rate", 0.0)),
            relative=case_relative,
            absolute=case_absolute,
        )
        if "pages" not in reference_case:
            continue
        actual_pages = {int(page["page"]): page for page in actual_case.get("pages") or []}
        reference_pages = {int(page["page"]): page for page in reference_case.get("pages") or []}
        for page_number in sorted(reference_pages.keys() - actual_pages.keys()):
            failures.append(f"{case_name} missing calibrated page: {page_number}")
        for page_number in sorted(actual_pages.keys() - reference_pages.keys()):
            failures.append(f"{case_name} unreviewed calibrated page: {page_number}")
        for page_number in sorted(reference_pages.keys() & actual_pages.keys()):
            _append_rate_regression(
                failures,
                label=f"{case_name} page {page_number} differing_rate",
                actual=float(actual_pages[page_number].get("differing_rate", 0.0)),
                reference=float(reference_pages[page_number].get("differing_rate", 0.0)),
                relative=page_relative,
                absolute=page_absolute,
            )
    return failures


def _append_rate_regression(
    failures: list[str],
    *,
    label: str,
    actual: float,
    reference: float,
    relative: float,
    absolute: float,
) -> None:
    limit = reference * (1.0 + relative) + absolute
    if actual <= limit:
        return
    failures.append(
        f"{label} regressed: actual={actual:.8f} reference={reference:.8f} limit={limit:.8f}"
    )


def compare_page_sets(
    case: HtmlCaseInputs,
    expected_pdf_pages: list[Image.Image],
    actual_html_pages: list[Image.Image],
    artifact_dir: Path,
) -> CaseFailure | None:
    """Compare canonical PDF page images to HTML screenshots."""
    if len(expected_pdf_pages) != len(actual_html_pages):
        _save_mismatch_pages(expected_pdf_pages, actual_html_pages, artifact_dir)
        return CaseFailure(
            case=case.case,
            artifact_dir=artifact_dir,
            summary=(
                f"HTML page count mismatch ({_case_category(case.name)}): "
                f"expected_pdf={len(expected_pdf_pages)} "
                f"actual_html={len(actual_html_pages)}"
            ),
        )

    failure_pages: list[PageDiff] = []
    for i, (expected, actual) in enumerate(zip(expected_pdf_pages, actual_html_pages, strict=True)):
        result = diff_pages(expected, actual)
        if result.pixels_differ <= case.html_tolerance_pixels:
            continue

        page_dir = artifact_dir / f"page_{i + 1:03d}"
        page_dir.mkdir(parents=True, exist_ok=True)
        expected_path = page_dir / "expected_pdf.png"
        actual_path = page_dir / "actual_html.png"
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

    if not failure_pages:
        return None

    return CaseFailure(
        case=case.case,
        artifact_dir=artifact_dir,
        pages=failure_pages,
        summary=(
            f"HTML: {len(failure_pages)} page(s) differ beyond "
            f"html_tolerance_pixels={case.html_tolerance_pixels}: "
            + ", ".join(f"p{page.index + 1}={page.pixels_differ}px" for page in failure_pages)
        ),
    )


def _case_category(case_name: str) -> str:
    if (
        case_name.startswith("06")
        or case_name.startswith("07")
        or case_name.startswith("08")
        or case_name.startswith("09")
        or case_name.startswith("10")
    ):
        return "category=table/listing"
    return "category=basic"


def _save_mismatch_pages(
    expected_pdf_pages: list[Image.Image],
    actual_html_pages: list[Image.Image],
    artifact_dir: Path,
) -> None:
    mismatch_dir = artifact_dir / "page_count_mismatch"
    mismatch_dir.mkdir(parents=True, exist_ok=True)
    for i, image in enumerate(expected_pdf_pages):
        image.convert("RGB").save(mismatch_dir / f"expected_pdf_{i + 1:03d}.png")
    for i, image in enumerate(actual_html_pages):
        image.convert("RGB").save(mismatch_dir / f"actual_html_{i + 1:03d}.png")
