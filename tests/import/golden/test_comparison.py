"""Golden comparison ignores layout padding, but never document changes."""

import pytest
from golden_harness import GoldenCase, _assert_markdown


@pytest.fixture(autouse=True)
def _skip_if_no_pandoc():
    """Comparison itself needs neither Pandoc nor parametrized DOCX fixtures."""
    return


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("- One\n\n- Two\n", "-   One\n\n-   Two\n"),
        ("| A | B |\n|---|---|\n| x | y |\n", "| A    | B   |\n|------|-----|\n| x    | y   |\n"),
    ],
)
def test_layout_padding_is_accepted(tmp_path, expected, actual):
    (tmp_path / "expected.md").write_text(expected)
    _assert_markdown(GoldenCase("padding", tmp_path), actual)


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("- One\n", "- Two\n"),
        ("- One\n  - Child\n", "- One\n- Child\n"),
        ("- One\n\n  continuation\n", "-   One\n\n  continuation\n"),
        ("| A | B |\n|:---|---:|\n", "| A | B |\n|---:|:---|\n"),
        ("```text\n- One\n```\n", "```text\n-   One\n```\n"),
        ("```text\n| A |\n|---|\n```\n", "```text\n| A   |\n|-----|\n```\n"),
        ("Text  with spaces.\n", "Text with spaces.\n"),
    ],
)
def test_content_and_structure_changes_are_rejected(tmp_path, expected, actual):
    (tmp_path / "expected.md").write_text(expected)
    with pytest.raises(AssertionError):
        _assert_markdown(GoldenCase("changed", tmp_path), actual)
