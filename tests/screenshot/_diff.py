"""Pixel diff between expected and actual page images, with red-overlay diff."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops


@dataclass(frozen=True)
class PageDiffResult:
    pixels_differ: int
    expected: Image.Image
    actual: Image.Image
    overlay: Image.Image


def diff_pages(expected: Image.Image, actual: Image.Image) -> PageDiffResult:
    """Compare two page images. `actual` is resized to match `expected` if needed."""
    expected_rgb = expected.convert("RGB")
    actual_rgb = actual.convert("RGB")
    if actual_rgb.size != expected_rgb.size:
        actual_rgb = actual_rgb.resize(expected_rgb.size)

    diff = ImageChops.difference(expected_rgb, actual_rgb)
    bbox = diff.getbbox()
    if bbox is None:
        empty_overlay = expected_rgb.copy()
        return PageDiffResult(0, expected_rgb, actual_rgb, empty_overlay)

    mask = diff.convert("L").point(lambda v: 255 if v > 0 else 0)
    pixels_differ = sum(1 for v in mask.getdata() if v)

    overlay = expected_rgb.copy()
    red = Image.new("RGB", expected_rgb.size, (255, 0, 0))
    overlay.paste(red, mask=mask)

    return PageDiffResult(pixels_differ, expected_rgb, actual_rgb, overlay)
