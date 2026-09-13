"""Build a final ``_report.pdf``.

Each failed case contributes:

- one page per pixel-diff page, side-by-side ``expected | actual | diff``;
- one extra page listing validation issues, if any.

A case with only validation issues (no pixel diffs) still produces a
validation page, so the report covers every failure mode.
"""

from __future__ import annotations

from pathlib import Path

from _pipeline import CaseFailure, PageDiff, ValidationIssue
from PIL import Image, ImageDraw, ImageFont

TRIPLE_GAP = 16
HEADER_HEIGHT = 40
PAGE_BG = (255, 255, 255)
HEADER_FG = (0, 0, 0)
ERROR_FG = (180, 0, 0)
WARNING_FG = (170, 110, 0)

SUMMARY_PAGE_SIZE = (1400, 900)
SUMMARY_LINE_HEIGHT = 24
SUMMARY_MARGIN = 40
SUMMARY_WRAP_WIDTH = 130
VALIDATION_PAGE_SIZE = (1400, 1800)
VALIDATION_LINE_HEIGHT = 22
VALIDATION_MARGIN = 40
VALIDATION_WRAP_WIDTH = 140  # rough char limit per line


def build_report(failures: list[CaseFailure], out_pdf: Path) -> None:
    """Render one PDF combining pixel-diff and validation pages for all failures."""
    pages: list[Image.Image] = []
    for failure in failures:
        for page_diff in failure.pages:
            pages.append(_compose_triple(failure.case.name, page_diff.index, page_diff))
        if failure.validation_issues:
            pages.append(_compose_validation_page(failure.case.name, failure.validation_issues))
        if not failure.pages and not failure.validation_issues:
            pages.append(_compose_summary_page(failure))

    if not pages:
        return

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    first, *rest = pages
    first.save(
        out_pdf,
        save_all=True,
        append_images=rest,
        format="PDF",
        resolution=100.0,
    )


def _compose_triple(case_name: str, page_index: int, page_diff: PageDiff) -> Image.Image:
    expected = Image.open(page_diff.expected_path).convert("RGB")
    actual = Image.open(page_diff.actual_path).convert("RGB")
    overlay = Image.open(page_diff.diff_path).convert("RGB")

    target_h = max(expected.height, actual.height, overlay.height)
    expected = _pad_to_height(expected, target_h)
    actual = _pad_to_height(actual, target_h)
    overlay = _pad_to_height(overlay, target_h)

    total_w = expected.width + actual.width + overlay.width + TRIPLE_GAP * 2
    total_h = target_h + HEADER_HEIGHT

    canvas = Image.new("RGB", (total_w, total_h), PAGE_BG)
    canvas.paste(expected, (0, HEADER_HEIGHT))
    canvas.paste(actual, (expected.width + TRIPLE_GAP, HEADER_HEIGHT))
    canvas.paste(overlay, (expected.width + actual.width + TRIPLE_GAP * 2, HEADER_HEIGHT))

    draw = ImageDraw.Draw(canvas)
    font = _load_font()
    title = (
        f"{case_name} — page {page_index + 1}  "
        f"(diff: {page_diff.pixels_differ} px)"
    )
    draw.text((8, 10), title, fill=HEADER_FG, font=font)
    draw.text((8, total_h - 18), _triple_label(page_diff), fill=HEADER_FG, font=font)
    return canvas


def _triple_label(page_diff: PageDiff) -> str:
    expected = "expected PDF" if "expected_pdf" in page_diff.expected_path.name else "expected"
    actual = "actual HTML" if "actual_html" in page_diff.actual_path.name else "actual"
    return f"{expected} | {actual} | diff (red)"


def _compose_summary_page(failure: CaseFailure) -> Image.Image:
    canvas = Image.new("RGB", SUMMARY_PAGE_SIZE, PAGE_BG)
    draw = ImageDraw.Draw(canvas)
    font = _load_font()
    bold = _load_font(size=20)

    y = SUMMARY_MARGIN
    draw.text(
        (SUMMARY_MARGIN, y),
        f"Screenshot failure — {failure.case.name}",
        fill=HEADER_FG,
        font=bold,
    )
    y += SUMMARY_LINE_HEIGHT + 12

    lines = [
        failure.summary,
        f"Artifacts: {failure.artifact_dir}",
    ]
    for line in lines:
        for wrapped in _wrap(line, SUMMARY_WRAP_WIDTH):
            draw.text((SUMMARY_MARGIN, y), wrapped, fill=HEADER_FG, font=font)
            y += SUMMARY_LINE_HEIGHT
    return canvas


def _compose_validation_page(
    case_name: str,
    issues: list[ValidationIssue],
) -> Image.Image:
    canvas = Image.new("RGB", VALIDATION_PAGE_SIZE, PAGE_BG)
    draw = ImageDraw.Draw(canvas)
    font = _load_font()
    bold = _load_font(size=20)

    y = VALIDATION_MARGIN
    draw.text(
        (VALIDATION_MARGIN, y),
        f"Validation issues — {case_name}",
        fill=HEADER_FG,
        font=bold,
    )
    y += VALIDATION_LINE_HEIGHT + 12

    for validator in sorted({i.validator for i in issues}):
        group = [i for i in issues if i.validator == validator]
        draw.text(
            (VALIDATION_MARGIN, y),
            f"[{validator}]  ({len(group)} issue{'s' if len(group) != 1 else ''})",
            fill=HEADER_FG,
            font=bold,
        )
        y += VALIDATION_LINE_HEIGHT + 4
        for issue in group:
            for line in _format_issue_lines(issue):
                color = ERROR_FG if issue.severity.value == "error" else WARNING_FG
                draw.text((VALIDATION_MARGIN + 16, y), line, fill=color, font=font)
                y += VALIDATION_LINE_HEIGHT
                if y > VALIDATION_PAGE_SIZE[1] - VALIDATION_MARGIN:
                    return canvas
        y += 8

    return canvas


def _format_issue_lines(issue: ValidationIssue) -> list[str]:
    location = f" ({issue.location})" if issue.location else ""
    head = f"[{issue.severity.value}] {issue.validator}.{issue.code} — {issue.message}{location}"
    return _wrap(head, VALIDATION_WRAP_WIDTH)


def _wrap(text: str, width: int) -> list[str]:
    """Naive wrap by width, preserving spaces."""
    if len(text) <= width:
        return [text]
    out: list[str] = []
    while len(text) > width:
        # Prefer breaking on the last space within window.
        cut = text.rfind(" ", 0, width)
        if cut <= 0:
            cut = width
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        out.append(text)
    return out


def _pad_to_height(img: Image.Image, height: int) -> Image.Image:
    if img.height == height:
        return img
    padded = Image.new("RGB", (img.width, height), PAGE_BG)
    padded.paste(img, (0, 0))
    return padded


def _load_font(size: int = 16) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()
