# Import postprocessor

Transformers in this package run after `pandoc` and reshape its output into
Markdown defined by the mandatory `docs/syntax.md` contract
(mapping details: `docs/import-syntax-mapping.md`). No legacy syntax is emitted.

## Representation

Each transformer operates on a **`list[str]` of markdown lines** — *not* on
the marko AST.

Rationale: pandoc with `markdown_strict+pipe_tables+bracketed_spans+…`
emits regular, line-oriented output. Regex on lines is simpler to debug than
a round-trip through marko and back to text, and it does not require us to
keep the import-side parser feature-compatible with the export side. The
trade-off — we cannot resolve constructs nested in lists or block-quotes —
is acceptable for the best-effort import contract (ADR-0006).

Each transformer must be a no-op inside fenced code blocks. Fence state is
tracked by toggling on lines matching `^\s*```` `…`.

## Pipeline order

`postprocessor.postprocess` runs transformers in this fixed order:

1. **`heading_normalizer`** — strips manual leading numbering
   `\d+(\.\d+)*\s+` from `#…#` headings.
2. **`unnumbered_heading_detector`** — known service headings
   (`СОДЕРЖАНИЕ` / `ВВЕДЕНИЕ` / `ЗАКЛЮЧЕНИЕ` /
   `СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ`) at level 1 receive `{.unnumbered}`.
3. **`html_table_converter`** (T046) — finds top-level
   `<table>…</table>` blocks pandoc emits for tables with
   `colspan`/`rowspan`/multi-paragraph cells and rewrites them as GFM
   pipe-tables. Flattens spans (no content duplication); joins
   `<p>`-paragraphs inside one cell with ` / `; preserves
   `<strong>`/`<em>`/`<u>`/`<code>` and inline `<img>`. Nested tables
   inside a `<td>` and any parser exception fall back to the original
   raw block, bumping
   `md2gost_import_fallback_total{stage=html_table}`. Runs **before**
   `caption_folder` so that `Таблица N — Caption` next to a converted
   table can still be folded into a trailing `: Caption`. Uses :mod:`html.parser`
   from stdlib — no new third-party dependency.
4. **`caption_folder`** — folds `Таблица/Рисунок/Листинг N — Caption`
   adjacent (above or below, up to two blank lines apart) to the target
   block into a universal trailing caption (`: Caption`) or, for
   images, into the image alt-text.
5. **`inline_normalizer`** — preserves `[text]{.underline}`; other
   pandoc bracketed-span attributes are dropped.

## Error policy

Any `Exception` raised by a transformer is caught at the line/block level,
the affected input is left untouched, and the counter
`md2gost_import_fallback_total{stage=<transformer name>}` is incremented
(also surfaced in `ImportResult.fallbacks`). The pipeline is **never**
aborted by a single bad block.
