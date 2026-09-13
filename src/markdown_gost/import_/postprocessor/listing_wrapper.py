"""Wrap monospace-paragraph ranges in fenced code blocks (T035).

The detector (:mod:`markdown_gost.import_.listing_detector`) returns runs of
monospace docx paragraphs *before* pandoc executes. After pandoc finishes,
this transformer locates the matching markdown lines (by literal text of the
first and last paragraph of the range) and wraps them in `` ``` ... ``` ``.

The fence is intentionally bare — language detection is out of scope, the
re-export side toggles syntax highlighting from config (see T035 task notes).
Any range that we fail to locate is skipped: the fallback metric is bumped
and the markdown is passed through unchanged, so a slightly drifted document
never aborts the import.

This transformer must run **before** :mod:`caption_folder` so that a
``Листинг N — Caption`` paragraph adjacent to a freshly wrapped fence is
folded into a trailing ``: Caption`` according to skills/markdown-gost/syntax.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..listing_detector import ParagraphRange
from ._common import bump_fallback

STAGE = "listing"


def transform(
    lines: list[str],
    fallbacks: dict[str, int],
    ranges: Sequence[ParagraphRange] | None = None,
) -> list[str]:
    if not ranges:
        return lines

    consumed = [False] * len(lines)
    wrap_spans: list[tuple[int, int]] = []
    search_from = 0

    for paragraph_range in ranges:
        try:
            span = _locate(lines, paragraph_range, consumed, search_from)
        except Exception:
            bump_fallback(fallbacks, STAGE)
            continue

        if span is None:
            bump_fallback(fallbacks, STAGE)
            continue

        start, end = span
        for idx in range(start, end + 1):
            consumed[idx] = True
        wrap_spans.append(span)
        search_from = end + 1

    if not wrap_spans:
        return lines

    return _apply_wraps(lines, wrap_spans)


def _locate(
    lines: list[str],
    paragraph_range: ParagraphRange,
    consumed: list[bool],
    search_from: int,
) -> tuple[int, int] | None:
    if not paragraph_range.texts:
        return None

    first_text = paragraph_range.texts[0]
    last_text = paragraph_range.texts[-1]

    start = _find_line(lines, first_text, search_from, consumed)
    if start is None:
        return None

    if len(paragraph_range.texts) == 1:
        return start, start

    end = _find_line(lines, last_text, start + 1, consumed)
    if end is None:
        return None

    return start, end


def _find_line(
    lines: list[str], needle: str, start: int, consumed: list[bool]
) -> int | None:
    target = needle.strip()
    if not target:
        return None
    for idx in range(start, len(lines)):
        if consumed[idx]:
            continue
        if lines[idx].strip() == target:
            return idx
    return None


def _apply_wraps(
    lines: list[str], wrap_spans: list[tuple[int, int]]
) -> list[str]:
    span_by_start = {start: end for start, end in wrap_spans}
    span_ends = {end for _, end in wrap_spans}
    out: list[str] = []
    idx = 0
    while idx < len(lines):
        if idx in span_by_start:
            out.append("```")
            end = span_by_start[idx]
            out.extend(lines[idx : end + 1])
            out.append("```")
            idx = end + 1
            continue
        # Defensive: an end-only span without a matching start shouldn't
        # happen because we own both ends, but be explicit.
        if idx in span_ends:
            out.append(lines[idx])
            idx += 1
            continue
        out.append(lines[idx])
        idx += 1
    return out


__all__ = ["STAGE", "transform"]
