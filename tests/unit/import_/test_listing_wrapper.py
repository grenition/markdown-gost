"""Unit tests for the listing wrapper transformer (T035)."""

from __future__ import annotations

import textwrap

from markdown_gost.import_.listing_detector import ParagraphRange
from markdown_gost.import_.postprocessor import listing_wrapper, postprocess


def _run(
    text: str, ranges: list[ParagraphRange]
) -> tuple[str, dict[str, int]]:
    fallbacks: dict[str, int] = {}
    lines = listing_wrapper.transform(text.split("\n"), fallbacks, ranges)
    return "\n".join(lines), fallbacks


def test_wraps_single_line_range_in_fences() -> None:
    src = "Prelude\n\nprint('hello')\n\nEpilogue"
    ranges = [ParagraphRange(start_index=2, texts=("print('hello')",))]

    out, fallbacks = _run(src, ranges)

    assert fallbacks == {}
    assert "```\nprint('hello')\n```" in out
    # The fenced block replaces the original line in place.
    assert out.count("print('hello')") == 1


def test_wraps_multi_line_range_in_one_fenced_block() -> None:
    src = textwrap.dedent(
        """\
        Intro.

        def f():
            return 1
            return 2

        Outro.
        """
    )
    ranges = [
        ParagraphRange(
            start_index=1,
            texts=("def f():", "    return 1", "    return 2"),
        )
    ]

    out, fallbacks = _run(src, ranges)

    assert fallbacks == {}
    expected_block = "```\ndef f():\n    return 1\n    return 2\n```"
    assert expected_block in out
    # Original lines wrapped — no orphan copies remain outside the fences.
    assert out.count("def f():") == 1


def test_skip_when_first_line_not_found_increments_fallback() -> None:
    src = "Prose only.\nNo code here.\n"
    ranges = [ParagraphRange(start_index=0, texts=("vanished line",))]

    out, fallbacks = _run(src, ranges)

    assert out == src
    assert fallbacks.get(listing_wrapper.STAGE) == 1


def test_skip_when_last_line_not_found_increments_fallback() -> None:
    src = "Prelude\nfirst code line\nsome prose between\n"
    ranges = [
        ParagraphRange(
            start_index=1, texts=("first code line", "missing tail")
        )
    ]

    out, fallbacks = _run(src, ranges)

    assert out == src
    assert fallbacks.get(listing_wrapper.STAGE) == 1


def test_no_ranges_is_noop() -> None:
    src = "Plain text.\n\nMore text.\n"
    out, fallbacks = _run(src, [])
    assert out == src
    assert fallbacks == {}


def test_wraps_multiple_independent_ranges() -> None:
    src = textwrap.dedent(
        """\
        intro

        first = 1

        between

        second = 2

        outro
        """
    )
    ranges = [
        ParagraphRange(start_index=1, texts=("first = 1",)),
        ParagraphRange(start_index=3, texts=("second = 2",)),
    ]

    out, fallbacks = _run(src, ranges)

    assert fallbacks == {}
    assert "```\nfirst = 1\n```" in out
    assert "```\nsecond = 2\n```" in out


def test_postprocess_threads_ranges_and_folds_caption() -> None:
    raw = textwrap.dedent(
        """\
        Листинг 1 — Echo

        print("hi")
        """
    )
    ranges = [ParagraphRange(start_index=2, texts=('print("hi")',))]

    out, fallbacks = postprocess(raw, monospace_ranges=ranges)

    assert fallbacks == {}
    assert ": Echo" in out
    assert "```\nprint(\"hi\")\n```" in out
    assert "Листинг 1 —" not in out


def test_postprocess_without_ranges_is_unchanged_for_listings() -> None:
    raw = "print('still prose without ranges')\n"
    out, fallbacks = postprocess(raw)
    assert "```" not in out
    assert fallbacks == {}
