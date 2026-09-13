# Architecture

markdown-gost is a Markdown → GOST document compiler with two renderers
(DOCX and HTML preview) sharing one layout engine.

```
                 ┌────────────────────────────────────────────────┐
 Markdown ──►    │ parser (marko extension)  →  extended AST       │
                 └───────────────┬────────────────────────────────┘
                                 │
                 ┌───────────────▼────────────────────────────────┐
                 │ renderable factory: AST → renderable tree       │
                 │ (paragraphs, headings, tables, listings,        │
                 │  equations, images, captions, appendices,       │
                 │  title-page templates, bibliography)            │
                 └───────────────┬────────────────────────────────┘
                                 │
              ┌──────────────────┴───────────────────┐
              ▼                                      ▼
   ┌──────────────────────┐               ┌──────────────────────┐
   │ DOCX renderer        │               │ preview builder      │
   │ render/renderer.py   │               │ preview/builder.py   │
   │ + layout tracker     │               │ (same layout engine, │
   │ + numberer, refs,    │               │  numberer, refs)     │
   │   bibliography       │               └──────────┬───────────┘
   └──────────┬───────────┘                          │
              ▼                                      ▼
        python-docx document                PreviewDocument model
              │                              + render_preview_html()
              ▼                                      │
        .docx file                     paginated HTML chunks, per-page
              │                        geometry, immutable assets
              ▼
        [unoserver, optional]
              ▼
        .pdf file
```

## Modules

| Path | Role |
|---|---|
| `core/parser/` | marko extension: attributes, sizing lists, GOST block syntax |
| `core/ast/` | extended AST node types |
| `renderable/` | one class per construct; emits DOCX paragraphs/tables |
| `render/` | document assembly: renderer, layout tracker, paragraph sizer (font metrics via fontconfig/freetype), heading/figure numbering, references, bibliography, LaTeX→OMML math |
| `preview/` | second renderer over the same layout engine: `build_preview_model()` → serializable `PreviewDocument`, `render_preview_html()` → chunked HTML |
| `output/pdf_writer.py` | thin XML-RPC client to a co-resident unoserver (LibreOffice). No HTTP server of its own |
| `import_/` | DOCX/PDF → Markdown: pandoc runner + semantic postprocessors (captions, headings, listings, tables), image extraction into storage |
| `storage/` | image backend protocol + built-in filesystem storage; services inject their own `Storage` implementations (object stores etc.) |
| `config/` | pydantic config schema + YAML presets (`default`, `gost-7-32-2017`, `mirea-practice`); no GOST rule is hardcoded |
| `templates/` | parameterized document skeletons (registry + JSON-schema-driven params), e.g. `titlepage-university` — a standard Russian university title page |
| `cli/` | Click CLI: `convert`, `validate`, `import` |
| `metrics_compat.py` | optional prometheus_client: no-op stand-ins when the service metrics stack is not installed |

## Key design points

- **One layout engine, two renderers.** The HTML preview is not an
  approximation: `preview/builder.py` reuses the DOCX pipeline's numberer,
  references and layout tracker, so page breaks match. A screenshot-suite
  overlay enforces pixel parity between HTML and DOCX→PDF output against
  committed baselines and reviewed calibration thresholds.
- **LibreOffice is optional and isolated.** Core DOCX generation is pure
  Python. PDF goes through a separate unoserver process (bundled in the
  Docker image, started by `docker/entrypoint.sh`), spoken to over
  XML-RPC on loopback.
- **Images via storage references, never inline.** Markdown references
  images by filesystem path (or an object key, when the integrating
  service injects its own `Storage` implementation); the converter pulls
  them through the `storage` abstraction. This keeps payloads small and
  works for storage-backed services.
- **Config over hardcoding.** Every visual rule lives in YAML config with
  presets; institutional variants are new preset files, not code.
- **Fonts are measured, not assumed.** `render/paragraph_sizer.py`
  measures real glyph metrics through fontconfig (Liberation/DejaVu in the
  image) to predict page breaks; see the README for host requirements.

## Testing tiers

1. `tests/unit/` — parser, renderables, config, preview model (fast).
2. `tests/integration/` — real conversion pipelines; unoserver tests skip
   when the server is unreachable.
3. `tests/import/{golden,roundtrip,smoke}/` — import fixtures with
   regenerate switches (`MARKDOWN_GOST_UPDATE_IMPORT_GOLDEN=1`).
4. `tests/screenshot/` — the merge gate: every case renders DOCX → PDF →
   raster and pixel-diffs against a committed `expected.pdf`; an HTML
   overlay captures the web preview through Playwright and diffs it against
   the same baseline within reviewed calibration thresholds
   (`html-calibration-*.json`). Regenerate deliberately via
   `MARKDOWN_GOST_UPDATE_BASELINES=1` and commit the reviewed diff.
