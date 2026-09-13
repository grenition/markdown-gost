"""Unit tests for the inline-span normalizer (T033)."""

from __future__ import annotations

from markdown_gost.import_.postprocessor import inline_normalizer


def _run(text: str) -> str:
    return "\n".join(inline_normalizer.transform(text.split("\n"), {}))


def test_underline_span_is_preserved() -> None:
    assert _run("This is [emphasised]{.underline} text") == (
        "This is [emphasised]{.underline} text"
    )


def test_multiple_underline_spans_on_one_line() -> None:
    out = _run("[A]{.underline} and [B]{.underline}")
    assert out == "[A]{.underline} and [B]{.underline}"


def test_underline_among_other_classes() -> None:
    out = _run("[X]{.smallcaps .underline}")
    assert out == "[X]{.underline}"


def test_unknown_attribute_class_is_stripped_to_plain_text() -> None:
    assert _run("[plain]{.smallcaps}") == "plain"


def test_regular_markdown_link_is_left_alone() -> None:
    assert _run("see [docs](https://example.com)") == (
        "see [docs](https://example.com)"
    )


def test_spans_inside_fenced_code_are_not_touched() -> None:
    src = "```\n[code]{.underline}\n```"
    assert _run(src) == src
