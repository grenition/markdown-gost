# markdown-gost

Markdown to GOST 7.32 DOCX/PDF converter with a paginated HTML preview.

- [Syntax reference](skills/markdown-gost/syntax.md) — extended Markdown: tables, listings, equations, appendices, bibliography, templates
- [Architecture](docs/architecture.md) — pipeline, config system, storage protocol, testing tiers

## Install

```bash
pipx install markdown-gost            # DOCX + preview
pipx install "markdown-gost[pdf]"     # + unoserver tooling
```

PDF output requires a running [unoserver](https://github.com/unoconv/unoserver)
(`pipx install unoserver && unoserver &`), reachable via `UNOSERVER_HOST` /
`UNOSERVER_PORT` (default `127.0.0.1:2003`).
Import requires pandoc >= 2.19 in PATH (`PANDOC_BINARY` to override).
Fonts for accurate pagination: `apt install fontconfig fonts-liberation
fonts-dejavu` (macOS: `brew install fontconfig font-liberation`).

Docker image with LibreOffice, unoserver, pandoc and fonts included:

```bash
docker run --rm -v "$PWD":/work -w /work ghcr.io/grenition/markdown-gost:0.1.0 \
  convert paper.md -o paper.docx
```

## Commands

```bash
markdown-gost convert input.md -o out.docx
markdown-gost convert input.md -o out.pdf                 # needs unoserver
markdown-gost convert input.md -o out.docx --config my.yaml
markdown-gost validate input.md
markdown-gost import legacy.docx -o imported.md           # needs pandoc
markdown-gost import legacy.pdf -o imported.md            # needs pandoc + unoserver
```

Config: YAML with presets (`default`, `gost-7-32-2017`, `mirea-practice`),
selected inside the file (`preset: gost-7-32-2017`), any field overridable.
Full schema: `markdown_gost.config.schema.Config.model_json_schema()`.

Preview API:

```python
from markdown_gost.preview import build_preview_model, render_preview_html

document = build_preview_model(markdown_text, config)
html = render_preview_html(document)
```

Object stores are not bundled: implement the `Storage` protocol and pass your
implementation to the conversion APIs.

## Agent skill

```bash
npx skills add grenition/markdown-gost          # skills.sh registry: Claude Code, Cursor, Codex, opencode, ...
cp -r skills/markdown-gost ~/.claude/skills/    # or copy into your harness skills directory
```

## Development

Python 3.13, Poetry 2.x.

```bash
poetry install
make test-unit
make test-integration
make test-screenshot      # pixel-diff merge gate
make lint typecheck
make test-in-docker       # full suite in the test image
```

## License

MIT — see [LICENSE](LICENSE).
