# markdown-gost

Convert Markdown into GOST-formatted **DOCX** and **PDF** documents — title
pages, numbered headings, captions, bibliographies, listings, equations and
everything else a Russian academic document needs — plus a paginated
**HTML preview** engine that renders in the browser without LibreOffice.

```bash
markdown-gost convert paper.md -o paper.docx
```

## Highlights

- **GOST 7.32–2017 out of the box** — page geometry, fonts, heading
  numbering, figure/table captions and structural sections (СОДЕРЖАНИЕ,
  ВВЕДЕНИЕ, ЗАКЛЮЧЕНИЕ, СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ).
- **Extended Markdown syntax** — attributes, image sizing, highlighted
  listings, LaTeX equations, appendices, GOST bibliography and more
  (see [docs/syntax.md](docs/syntax.md)).
- **Templates** — reusable document skeletons (e.g. a standard Russian
  university title page) parameterized from Markdown.
- **HTML preview** — a second renderer over the same layout engine:
  page-accurate, chunked, browser-ready — ideal for web editors.
- **Import back** — `markdown-gost import` converts existing DOCX/PDF files
  into the extended Markdown (via pandoc + a semantic postprocessor).
- **Zero services for DOCX** — the core pipeline is a plain Python library;
  LibreOffice is only needed for PDF.
- **Tested in pixels** — a screenshot suite renders every feature through
  the real DOCX→PDF pipeline and diffs it against committed baselines, with
  an HTML-parity overlay keeping the web preview faithful to the document.

## Installation

### pipx / pip (DOCX + preview)

```bash
pipx install markdown-gost
```

Optional extras:

```bash
pipx install "markdown-gost[pdf]"   # + unoserver tooling for PDF output
```

Object stores are not bundled: implement the `Storage` protocol and pass
your implementation to the conversion APIs (see
[docs/architecture.md](docs/architecture.md)).

PDF conversion additionally requires a running
[unoserver](https://github.com/unoconv/unoserver) instance
(`pipx install unoserver && unoserver &`) reachable at
`UNOSERVER_HOST:UNOSERVER_PORT` (default `127.0.0.1:2003`).

**Fonts.** Layout measurement uses fontconfig. For pixel-accurate pagination
install metric-compatible fonts (Liberation, DejaVu):

- Debian/Ubuntu: `apt install fontconfig fonts-liberation fonts-dejavu`
- macOS: `brew install fontconfig font-liberation`

Without them the document is still produced, but page-break estimates may
drift by a few percent.

### Docker (everything included)

```bash
docker run --rm -v "$PWD":/work -w /work ghcr.io/grenition/markdown-gost:0.1.0 \
  convert paper.md -o paper.docx
```

The image bundles LibreOffice, unoserver, pandoc and pinned fonts, so DOCX,
PDF and DOCX-import all work with zero local setup.

## Usage

### Convert and validate

```bash
markdown-gost convert input.md -o out.docx
markdown-gost convert input.md -o out.pdf            # needs unoserver
markdown-gost convert input.md -o out.docx --config my-config.yaml
markdown-gost validate input.md
```

### Import an existing document

```bash
markdown-gost import legacy.docx -o imported.md      # needs pandoc >= 2.19
markdown-gost import legacy.pdf  -o imported.md      # needs pandoc + unoserver
```

### Configuration

Rendering is fully parameterized through YAML configs with presets; no
GOST rule is hardcoded. Built-in presets: `default`, `gost-7-32-2017`,
`mirea-practice`. A preset is selected inside the config file:

```yaml
preset: gost-7-32-2017
```

and any field can be overridden below it. The JSON Schema of every field is
available programmatically via
`markdown_gost.config.schema.Config.model_json_schema()`.

### HTML preview (library API)

```python
from markdown_gost.preview import build_preview_model, render_preview_html

document = build_preview_model(markdown_text, config)
html = render_preview_html(document)          # full standalone page
```

The preview model is page-accurate (it shares the layout engine with the
DOCX renderer), serializable, and renders per-page chunks — see
[docs/architecture.md](docs/architecture.md).

## Development

Python 3.13, Poetry 2.x.

```bash
poetry install
make test-unit          # fast tests
make test-integration   # needs dockerized unoserver/MinIO — or use make test-in-docker
make test-screenshot    # pixel-diff gate over the real DOCX→PDF pipeline
make lint typecheck
```

`make test-in-docker` runs the entire suite inside the test image with
LibreOffice, fonts and Playwright preinstalled — the same environment CI
uses.

## License

MIT — see [LICENSE](LICENSE).
