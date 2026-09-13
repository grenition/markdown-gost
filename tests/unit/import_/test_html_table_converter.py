"""Unit tests for the raw-HTML ``<table>`` → pipe-table transformer (T046)."""

from __future__ import annotations

import textwrap

from markdown_gost.import_.postprocessor import html_table_converter


def _run(text: str) -> tuple[str, dict[str, int]]:
    fallbacks: dict[str, int] = {}
    out = html_table_converter.transform(text.split("\n"), fallbacks)
    return "\n".join(out), fallbacks


def test_simple_two_by_two_no_thead() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td>A</td><td>B</td></tr>
        <tr><td>C</td><td>D</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out == textwrap.dedent(
        """\
        | A | B |
        |---|---|
        | C | D |"""
    )


def test_thead_promotes_header_row_with_separator() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <thead>
        <tr><th>H1</th><th>H2</th></tr>
        </thead>
        <tbody>
        <tr><td>x</td><td>y</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out == textwrap.dedent(
        """\
        | H1 | H2 |
        |---|---|
        | x | y |"""
    )


def test_colspan_flattens_with_trailing_empty_cells() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td>A</td><td>B</td><td>C</td></tr>
        <tr><td colspan="3">Объединённый</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out == textwrap.dedent(
        """\
        | A | B | C |
        |---|---|---|
        | Объединённый |  |  |"""
    )


def test_university_titlepage_with_image_and_colspan() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <colgroup>
        <col style="width: 27%" />
        <col style="width: 33%" />
        <col style="width: 38%" />
        </colgroup>
        <tbody>
        <tr class="odd">
        <td><strong><br />
        </strong></td>
        <td>![](images/bcf63d1fa8b0dea9237435ab33917638)</td>
        <td></td>
        </tr>
        <tr class="even">
        <td colspan="3">МИНОБРНАУКИ РОССИИ</td>
        </tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    lines = out.split("\n")
    # Header row: empty strong cell (with the ` / ` from <br/>), then the image,
    # then an empty cell.
    assert lines[0].count("|") == 4
    assert "![](images/bcf63d1fa8b0dea9237435ab33917638)" in lines[0]
    assert lines[1] == "|---|---|---|"
    # colspan="3" → text in first column, two empty cells trailing.
    assert lines[2].startswith("| МИНОБРНАУКИ РОССИИ |")
    assert lines[2].endswith("|  |  |")


def test_rowspan_flattens_with_empty_cells_below() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td rowspan="2">A</td><td>B</td></tr>
        <tr><td>C</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out == textwrap.dedent(
        """\
        | A | B |
        |---|---|
        |  | C |"""
    )


def test_multi_paragraph_cell_joined_with_slash() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td><p>A</p><p>B</p></td><td>x</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    # First row promoted to header; ` / ` separates the two paragraphs.
    assert out.split("\n")[0] == "| A / B | x |"


def test_image_inside_cell_preserved_as_markdown() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td><img src="media/image1.png" alt="logo" /></td><td>text</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out.split("\n")[0] == "| ![logo](media/image1.png) | text |"


def test_inline_formatting_mapped_to_markdown() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td><strong>bold</strong></td><td><em>it</em></td><td><u>u</u></td><td><code>c</code></td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out.split("\n")[0] == "| **bold** | *it* | [u]{.underline} | `c` |"


def test_empty_inline_wrapper_is_dropped() -> None:
    # ``<strong><br/></strong>`` would otherwise become ``** / **`` which
    # looks like broken bold. The converter collapses empty wrappers and
    # leaves only the inner content (the line-break separator).
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td><strong><br /></strong></td><td>x</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    # The empty <strong> wrapper around the lone <br/> is gone; the cell
    # ends up effectively empty (the slash falls off because text() strips).
    first = out.split("\n")[0]
    assert "**" not in first
    assert first.endswith("| x |")


def test_broken_html_falls_back_and_increments_metric() -> None:
    # Unterminated <table> — converter must leave the line intact and bump
    # the fallback counter.
    src = "<table>\nbroken contents without close"
    out, fallbacks = _run(src)
    assert fallbacks == {"html_table": 1}
    assert out == "<table>\nbroken contents without close"


def test_nested_table_falls_back_keeps_outer_block() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td>
        <table>
        <tbody><tr><td>inner</td></tr></tbody>
        </table>
        </td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {"html_table": 1}
    # Original block kept verbatim — no pipe-table emitted.
    assert "|---|" not in out
    assert "<table>" in out
    assert "</table>" in out


def test_pipe_character_inside_cell_is_escaped() -> None:
    src = textwrap.dedent(
        """\
        <table>
        <tbody>
        <tr><td>a|b</td><td>c</td></tr>
        </tbody>
        </table>"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out.split("\n")[0] == r"| a\|b | c |"


def test_fenced_code_block_with_table_syntax_is_left_alone() -> None:
    src = textwrap.dedent(
        """\
        ```html
        <table>
        <tr><td>not converted</td></tr>
        </table>
        ```"""
    )
    out, fallbacks = _run(src)
    assert fallbacks == {}
    assert out == src
