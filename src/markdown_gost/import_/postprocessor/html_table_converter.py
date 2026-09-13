"""Convert raw HTML ``<table>`` blocks from pandoc into GFM pipe-tables.

Pandoc falls back to raw HTML for any DOCX table it cannot express as
``pipe_tables`` — typically tables with ``colspan``/``rowspan``,
multi-paragraph cells, embedded images or ``colgroup``-driven widths.
Such tables otherwise reach marko as opaque raw HTML and disappear from
the rendered output (see T046 and ``docs/import-syntax-mapping.md`` §2.6).

This transformer locates every top-level ``<table>…</table>`` block in
the pandoc output, parses it with :mod:`html.parser` (no new
dependency), and rewrites it as a GFM pipe-table:

* number of columns = maximum row width once ``colspan`` is summed;
* ``<thead>`` becomes the header row; absent that, the first row is
  promoted and a synthetic separator is inserted under it;
* ``colspan="N"`` flattens to the original cell plus ``N-1`` empty cells
  to its right; ``rowspan="N"`` flattens to one empty cell below per
  extra row at the same column index (no content duplication);
* ``<p>`` paragraphs inside a single cell are joined by `` / `` —
  markdown-gost's renderer collapses ``LineBreak`` to a space, so a real
  ``<br>`` would not survive (see T046a);
* ``<strong>`` / ``<em>`` / ``<u>`` / ``<code>`` map to their markdown
  counterparts; ``<img>`` becomes ``![alt](src)``.

A nested ``<table>`` inside any ``<td>`` is not expressible in
pipe-tables and triggers a fallback for the whole outer block. Any
exception during parsing leaves the original lines untouched and
increments ``md2gost_import_fallback_total{stage=html_table}``.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from ._common import CODE_FENCE_RE, bump_fallback

STAGE = "html_table"

_TABLE_OPEN_RE = re.compile(r"^\s*<table(?:\s[^>]*)?>\s*$", re.IGNORECASE)
_TABLE_CLOSE_RE = re.compile(r"^\s*</table>\s*$", re.IGNORECASE)
_INLINE_WS_RE = re.compile(r"\s+")
_SLASH_RUN_RE = re.compile(r"(?:\s*/\s*){2,}")


def transform(lines: list[str], fallbacks: dict[str, int]) -> list[str]:
    out: list[str] = []
    in_code = False
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            out.append(line)
            i += 1
            continue
        if in_code or not _TABLE_OPEN_RE.match(line):
            out.append(line)
            i += 1
            continue

        end = _find_table_end(lines, i)
        if end is None:
            # Unterminated <table> — leave as raw, do not block import.
            bump_fallback(fallbacks, STAGE)
            out.append(line)
            i += 1
            continue

        block = lines[i : end + 1]
        try:
            converted = _convert_block(block)
        except Exception:
            bump_fallback(fallbacks, STAGE)
            out.extend(block)
            i = end + 1
            continue

        if converted is None:
            bump_fallback(fallbacks, STAGE)
            out.extend(block)
        else:
            out.extend(converted)
        i = end + 1
    return out


def _find_table_end(lines: list[str], start: int) -> int | None:
    depth = 0
    for j in range(start, len(lines)):
        if _TABLE_OPEN_RE.match(lines[j]):
            depth += 1
        if _TABLE_CLOSE_RE.match(lines[j]):
            depth -= 1
            if depth == 0:
                return j
    return None


# ---------------------------------------------------------------------------
# HTML → grid
# ---------------------------------------------------------------------------


class _Cell:
    __slots__ = ("colspan", "fmt_stack", "is_header", "p_count", "parts", "rowspan")

    def __init__(self, colspan: int, rowspan: int, is_header: bool) -> None:
        self.colspan = colspan
        self.rowspan = rowspan
        self.is_header = is_header
        self.parts: list[str] = []
        self.p_count = 0
        # Stack entries: (html_tag, markdown_marker, parts_index_of_open_marker)
        self.fmt_stack: list[tuple[str, str, int]] = []

    def text(self) -> str:
        raw = "".join(self.parts)
        # Collapse whitespace runs and trim, then normalise the ` / `
        # separators we synthesised for ``<br>`` and multi-``<p>`` cells:
        # strip leading/trailing slashes and collapse runs (an empty
        # paragraph would otherwise leave ``A /  / B`` in the cell).
        collapsed = _INLINE_WS_RE.sub(" ", raw).strip()
        collapsed = _SLASH_RUN_RE.sub("/", collapsed)
        collapsed = collapsed.strip(" /").strip()
        return collapsed.replace("|", r"\|")


class _TableParser(HTMLParser):
    """Collect rows of cells from a single ``<table>`` HTML fragment.

    Nested tables inside a ``<td>`` are rejected by setting :attr:`aborted`;
    the caller falls back to leaving the original HTML untouched.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_Cell]] = []
        self.has_thead = False
        self.aborted = False
        self._depth = 0
        self._in_thead = False
        self._current_row: list[_Cell] | None = None
        self._cell_stack: list[_Cell] = []

    # -- structural tags ----------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.aborted:
            return
        tag = tag.lower()
        if tag == "table":
            self._depth += 1
            if self._depth > 1:
                # Nested table inside outer table — pipe-tables cannot express it.
                self.aborted = True
            return
        if tag == "thead":
            self.has_thead = True
            self._in_thead = True
            return
        if tag == "tbody" or tag == "tfoot":
            return
        if tag == "colgroup" or tag == "col":
            return
        if tag == "tr":
            self._current_row = []
            return
        if tag in ("td", "th"):
            attrd = _attrs_dict(attrs)
            colspan = _parse_span(attrd.get("colspan"))
            rowspan = _parse_span(attrd.get("rowspan"))
            cell = _Cell(
                colspan=colspan,
                rowspan=rowspan,
                is_header=(tag == "th" or self._in_thead),
            )
            self._cell_stack.append(cell)
            return
        # Inline element inside a cell.
        if not self._cell_stack:
            return
        cell = self._cell_stack[-1]
        if tag in ("strong", "b"):
            cell.fmt_stack.append((tag, "**", len(cell.parts)))
            cell.parts.append("**")
        elif tag in ("em", "i"):
            cell.fmt_stack.append((tag, "*", len(cell.parts)))
            cell.parts.append("*")
        elif tag == "u":
            cell.fmt_stack.append((tag, "]{.underline}", len(cell.parts)))
            cell.parts.append("[")
        elif tag == "code":
            cell.fmt_stack.append((tag, "`", len(cell.parts)))
            cell.parts.append("`")
        elif tag == "br":
            cell.parts.append(" / ")
        elif tag == "p":
            if cell.p_count > 0:
                cell.parts.append(" / ")
            cell.p_count += 1
        elif tag == "img":
            self._emit_img(cell, attrs)
        # Other inline tags (span, div, …): structurally invisible.

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.aborted:
            return
        tag = tag.lower()
        if tag == "col":
            return
        if tag == "br" and self._cell_stack:
            self._cell_stack[-1].parts.append(" / ")
            return
        if tag == "img" and self._cell_stack:
            self._emit_img(self._cell_stack[-1], attrs)
            return

    def handle_endtag(self, tag: str) -> None:
        if self.aborted:
            return
        tag = tag.lower()
        if tag == "table":
            self._depth -= 1
            return
        if tag == "thead":
            self._in_thead = False
            return
        if tag in ("tbody", "tfoot", "colgroup", "col"):
            return
        if tag == "tr":
            if self._current_row is not None:
                self.rows.append(self._current_row)
                self._current_row = None
            return
        if tag in ("td", "th"):
            if self._cell_stack:
                cell = self._cell_stack.pop()
                if self._current_row is not None:
                    self._current_row.append(cell)
            return
        if not self._cell_stack:
            return
        cell = self._cell_stack[-1]
        if cell.fmt_stack and cell.fmt_stack[-1][0] == tag:
            _, marker, open_idx = cell.fmt_stack.pop()
            inner = "".join(cell.parts[open_idx + 1 :])
            # Treat wrappers whose only content is whitespace or synthesised
            # ``/`` break separators as empty — otherwise
            # ``<strong><br/></strong>`` would emit a bogus ``** / **``.
            if inner.strip(" /\t\n") == "":
                del cell.parts[open_idx:]
                cell.parts.append(inner)
            else:
                cell.parts.append(marker)

    def handle_data(self, data: str) -> None:
        if self.aborted or not self._cell_stack:
            return
        self._cell_stack[-1].parts.append(data)

    def _emit_img(self, cell: _Cell, attrs: list[tuple[str, str | None]]) -> None:
        attrd = _attrs_dict(attrs)
        src = attrd.get("src", "") or ""
        alt = attrd.get("alt", "") or ""
        cell.parts.append(f"![{alt}]({src})")


def _attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {k.lower(): (v or "") for k, v in attrs}


def _parse_span(value: str | None) -> int:
    if not value:
        return 1
    try:
        n = int(value.strip())
    except ValueError:
        return 1
    return max(n, 1)


# ---------------------------------------------------------------------------
# Grid → pipe-table
# ---------------------------------------------------------------------------


def _convert_block(block: list[str]) -> list[str] | None:
    """Return pipe-table lines, ``None`` to signal fallback (kept raw)."""
    html_text = "\n".join(block)
    parser = _TableParser()
    parser.feed(html_text)
    parser.close()
    if parser.aborted:
        return None
    if not parser.rows:
        return None

    grid = _flatten_to_grid(parser.rows)
    if not grid or not grid[0]:
        return None

    n_cols = len(grid[0])
    out: list[str] = []
    header = grid[0]
    out.append(_format_row(header))
    out.append("|" + "|".join("---" for _ in range(n_cols)) + "|")
    for row in grid[1:]:
        out.append(_format_row(row))
    return out


def _flatten_to_grid(rows: list[list[_Cell]]) -> list[list[str]]:
    # First pass: compute placements and column count.
    occupied: dict[tuple[int, int], bool] = {}
    placements: list[tuple[int, int, _Cell]] = []
    max_col = 0
    extra_rows = 0
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            placements.append((r, c, cell))
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    occupied[(r + dr, c + dc)] = True
            if r + cell.rowspan - 1 > len(rows) - 1 + extra_rows:
                extra_rows = (r + cell.rowspan - 1) - (len(rows) - 1)
            c += cell.colspan
            if c > max_col:
                max_col = c
    if max_col == 0:
        return []
    n_rows = len(rows) + max(extra_rows, 0)

    grid = [["" for _ in range(max_col)] for _ in range(n_rows)]
    for r, c, cell in placements:
        grid[r][c] = cell.text()
    return grid


def _format_row(row: list[str]) -> str:
    return "| " + " | ".join(row) + " |"


__all__ = ["STAGE", "transform"]
