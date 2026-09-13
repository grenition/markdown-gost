# Import golden tests (T038)

Snapshot tests for the DOCX → markdown import pipeline. Each fixture is a
self-contained directory; the harness runs `import_docx()` against
`input.docx` and diffs the resulting markdown against `expected.md`.

The syntax contract is [docs/syntax.md](../../../docs/syntax.md).
Comparison is exact except for Pandoc-version-dependent padding after top-level
bullet markers and inside pipe tables (including separator dash counts).
Those differences are accepted only when the parsed AST is also identical.
Text, code, nesting, cell contents, alignment and attributes remain checked.
The comparison unit tests exercise both accepted padding and rejected changes.

```
tests/import/golden/
├── conftest.py          — pytest plugin: discovery + pandoc skip-guard
├── harness.py           — run_import_golden + discover_cases
├── test_golden.py       — single parametrized test
├── README.md            — this file
├── 01-simple-text/
│   ├── generate.py      — reproducible builder (python-docx)
│   ├── input.docx       — committed fixture
│   ├── expected.md      — committed baseline
│   └── expected_files/  — optional; image filenames only
├── 02-headings/
…
```

## Running

```bash
make test-import-golden
# or directly:
poetry run pytest tests/import/golden -v
```

The whole module is skipped if pandoc isn't on `PATH` — same guard used by
the rest of `tests/integration/test_*_import_*.py`.

## Adding a new case

1. `mkdir tests/import/golden/09-my-case`
2. Add `generate.py` that builds `input.docx` deterministically — reuse
   the pattern from existing cases (`python-docx` for body content;
   lxml-injected OMML XML for math).
3. Run the generator once: `poetry run python tests/import/golden/09-my-case/generate.py`.
4. Generate the baseline: `make import-golden-baseline` (or
   `MD2GOST_UPDATE_IMPORT_GOLDEN=1 pytest tests/import/golden -v`).
5. **Audit `expected.md` by eye** before committing — it's a frozen snapshot
   of what the pipeline produces today, including any rough edges. Once
   committed, every future change to the pipeline that touches your case
   will show up in the diff.

## Regenerating a baseline

Only do this when:

* You deliberately changed the import pipeline (postprocessor, listing
  detector, image handler, …), **and**
* You diffed the new `expected.md` against the old one and confirmed every
  change is intentional, **and**
* The user explicitly approved the regen (see the project-wide screenshot
  baseline policy — same rule applies here).

```bash
MD2GOST_UPDATE_IMPORT_GOLDEN=1 poetry run pytest tests/import/golden -v
git diff tests/import/golden   # audit before commit
```

## What the harness checks

* `actual_markdown == expected_md` (exact byte match; unified diff printed
  on failure).
* `sorted(images_dir/*) == sorted(expected_files/*)` — image **names** only.
  Bytes aren't compared because docx-embedded images may be re-encoded by
  pandoc.

## Notes

* `expected.md` is committed verbatim — including pandoc artefacts like
  `<!-- -->` separators between sibling lists or `<s>…</s>` for strike.
  Improving those is a postprocessor task, not a harness task; when you
  improve them the baseline updates and the diff documents the change.
* All import test trees (golden / roundtrip / smoke) live under
  `tests/import/` so they share the `requires_pandoc` plumbing and stay
  out of the broader `tests/integration/` tree.
