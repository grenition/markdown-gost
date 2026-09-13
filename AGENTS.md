# AGENTS.md — markdown-gost

## Map

- `src/markdown_gost/` — package (src-layout; tests run against the installed copy)
- `skills/markdown-gost/syntax.md` — normative syntax contract **and** executable corpus
- `tests/` — `unit/` fast, `integration/` (unoserver/pandoc), `import/` (golden, roundtrip), `screenshot/` pixel gate
- `docker/` — image (Dockerfile + entrypoint with unoserver)
- `skills/markdown-gost/` — installable agent skill (see sync test)

## Commands

```bash
poetry install
make test-unit          # fast
make test-integration   # needs unoserver + pandoc (or make test-in-docker)
make test-screenshot    # pixel-diff merge gate
make lint typecheck
make test-in-docker     # full suite inside the test image
```

## Rules

1. Syntax changes: update `skills/markdown-gost/syntax.md` and the acceptance tests FIRST,
   then the parser. Fenced `markdown` blocks in that file are parsed by
   `tests/unit/parser/test_full_corpus.py` — a construct without a live
   example there is not covered.
2. Screenshot suite is the merge gate. On failure: stop, review the
   rendered diff manually. Regenerate baselines
   (`MARKDOWN_GOST_UPDATE_BASELINES=1`) only for deliberate, reviewed
   rendering changes — never to make a diff disappear.
3. No GOST rule is hardcoded: layout, numbering and captions live in the
   YAML config with presets (`src/markdown_gost/config/presets/`).
4. Images and logos are references (paths/URLs/storage keys), never
   inline payloads.
5. Tests before implementation; unit + lint + typecheck green before done.
6. `skills/markdown-gost/syntax.md` must stay identical to
   `skills/markdown-gost/syntax.md` (enforced by a unit test).

## Style

Write everything short: docs, comments, commit messages, code. Brevity is
a feature, not a courtesy. Conventional commits.

## Releases

Automated by python-semantic-release on push to main: `feat` → minor,
`fix`/`perf` → patch, `feat!` or a `BREAKING CHANGE` footer → major
(even at 0.x). Versions are stamped into `pyproject.toml` and
`__version__` automatically — never bump or tag manually.
