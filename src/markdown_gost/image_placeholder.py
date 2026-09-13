"""Shared, self-contained representation for unavailable images."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageDraw

PLACEHOLDER_COPY = "Изображение не загружено"


def placeholder_copy(alt: str | None = None) -> str:
    """Return generic fallback copy, optionally qualified by authored alt text."""

    return f"{PLACEHOLDER_COPY}: {alt}" if alt else PLACEHOLDER_COPY


@lru_cache(maxsize=1)
def placeholder_svg() -> bytes:
    """Return a neutral standalone SVG with no scripts or external resources."""

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" '
        'role="img" aria-label="Изображение не загружено">'
        '<rect x="1.5" y="1.5" width="637" height="357" rx="4" '
        'fill="#fafafa" stroke="#777" stroke-width="3"/>'
        '<g fill="none" stroke="#555" stroke-width="8">'
        '<rect x="242" y="80" width="156" height="130"/>'
        '<circle cx="280" cy="122" r="14" fill="#555" stroke="none"/>'
        '<path d="M258 192l49-54 36 35 39-52"/>'
        "</g>"
        '<text x="320" y="265" text-anchor="middle" fill="#555" '
        'font-family="Arial, sans-serif" font-size="24">'
        "Изображение не загружено"
        "</text>"
        "</svg>"
    ).encode()


@lru_cache(maxsize=1)
def placeholder_png() -> bytes:
    """Return a neutral 16:9 icon card suitable for embedding in a DOCX."""

    width, height = 640, 360
    image = PILImage.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    border = (119, 119, 119)
    accent = (85, 85, 85)
    draw.rectangle((1, 1, width - 2, height - 2), outline=border, width=3)

    icon_left, icon_top, icon_right, icon_bottom = 242, 105, 398, 235
    draw.rectangle(
        (icon_left, icon_top, icon_right, icon_bottom),
        outline=accent,
        width=8,
    )
    draw.ellipse((icon_left + 24, icon_top + 22, icon_left + 52, icon_top + 50), fill=accent)
    draw.line(
        (
            icon_left + 16,
            icon_bottom - 18,
            icon_left + 65,
            icon_top + 76,
            icon_left + 101,
            icon_bottom - 18,
            icon_right - 16,
            icon_top + 56,
        ),
        fill=accent,
        width=8,
        joint="curve",
    )

    buffer = BytesIO()
    image.save(buffer, format="PNG", dpi=(96, 96))
    return buffer.getvalue()
