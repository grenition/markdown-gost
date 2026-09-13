"""Unit tests for the unnumbered service-heading detector (T033)."""

from __future__ import annotations

from markdown_gost.import_.postprocessor import unnumbered_heading_detector


def _run(text: str) -> str:
    return "\n".join(
        unnumbered_heading_detector.transform(text.split("\n"), {})
    )


def test_marks_soderzhanie() -> None:
    assert _run("# СОДЕРЖАНИЕ") == "# СОДЕРЖАНИЕ {.unnumbered}"


def test_marks_vvedenie_case_insensitive() -> None:
    assert _run("# Введение") == "# Введение {.unnumbered}"


def test_marks_full_bibliography_phrase() -> None:
    out = _run("# Список использованных источников")
    assert out == "# Список использованных источников {.unnumbered}"


def test_does_not_touch_h2_with_same_text() -> None:
    assert _run("## ВВЕДЕНИЕ") == "## ВВЕДЕНИЕ"


def test_does_not_touch_unrelated_h1() -> None:
    assert _run("# Содержание главы") == "# Содержание главы"


def test_does_not_double_star_an_already_unnumbered_heading() -> None:
    assert _run("# *СОДЕРЖАНИЕ") == "# *СОДЕРЖАНИЕ"
