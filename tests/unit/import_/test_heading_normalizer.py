"""Unit tests for the heading-numbering normalizer (T033)."""

from __future__ import annotations

from markdown_gost.import_.postprocessor import heading_normalizer


def _run(text: str) -> tuple[str, dict[str, int]]:
    fallbacks: dict[str, int] = {}
    lines = heading_normalizer.transform(text.split("\n"), fallbacks)
    return "\n".join(lines), fallbacks


def test_strips_single_digit_h1() -> None:
    out, fb = _run("# 1 Введение")
    assert out == "# Введение"
    assert fb == {}


def test_strips_dotted_numbering_h2() -> None:
    out, _ = _run("## 1.2 Метод исследования")
    assert out == "## Метод исследования"


def test_strips_three_level_numbering_h3() -> None:
    out, _ = _run("### 2.3.4 Глубокий заголовок")
    assert out == "### Глубокий заголовок"


def test_leaves_unnumbered_heading_untouched() -> None:
    out, _ = _run("# *Без нумерации")
    assert out == "# *Без нумерации"


def test_leaves_paragraph_starting_with_digit_untouched() -> None:
    out, _ = _run("В 2024 году произошло событие")
    assert out == "В 2024 году произошло событие"


def test_no_op_inside_fenced_code() -> None:
    src = "```\n# 1 Like a heading but it is code\n```"
    out, _ = _run(src)
    assert out == src
