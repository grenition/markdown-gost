# CHANGELOG


## v0.2.1 (2026-09-13)

### Bug Fixes

- **ci**: Set up buildx before pushing the runtime image
  ([`83edc0b`](https://github.com/grenition/markdown-gost/commit/83edc0b7c34c38075f9732b5eefb64e7e5bdee1b))

The gha build cache requires the buildx driver; the release job ran on the plain docker driver and
  failed the cache export.

- **tests**: Derive expected version dynamically in CLI version tests
  ([`44eb490`](https://github.com/grenition/markdown-gost/commit/44eb4909ce476ca5b92fc9db854ef8d01bb91442))

Hardcoded 0.1.0 broke on every semantic-release bump; the smoke test now compares __version__
  against pyproject via tomllib, CLI tests assert the imported package version.


## v0.2.0 (2026-09-13)

### Bug Fixes

- License date
  ([`2f1e9b4`](https://github.com/grenition/markdown-gost/commit/2f1e9b411495a85ef7bf04a2af2007651a081072))

- **ci**: Build dists with python -m build inside the release action
  ([`b0963ea`](https://github.com/grenition/markdown-gost/commit/b0963ea09f3b04551e5f760fe9593d7a72b4615e))

pipx is not available in the semantic-release action container (exit 127); python -m build drives
  the poetry-core backend directly through PEP 517.

- **ci**: Pin upload-to-gh-release to an existing tag
  ([`c268493`](https://github.com/grenition/markdown-gost/commit/c26849328e7b719128bee83d43806e795b188f47))

- **ci**: Use the semantic-release version action, not publish-action
  ([`cf65e6c`](https://github.com/grenition/markdown-gost/commit/cf65e6c7f09809be810f6fd5663faf908937d2c7))

publish-action only uploads distributions to an existing release; the version action
  (semantic-release version) computes the bump, stamps the version, builds, tags, pushes and creates
  the GitHub release.

- **tests**: Replace bare conftest imports in the screenshot suite
  ([`0567270`](https://github.com/grenition/markdown-gost/commit/05672708db4552e8d4136a8ad3cfb53018f00bd2))

The full single-process pytest run (the CI image entrypoint) collects tests/import/smoke/conftest.py
  as the top-level 'conftest' module first, so 'from conftest import ARTIFACTS_DIR' in screenshot
  tests resolved to the wrong module and broke collection. The path constants now live in
  _pipeline.py; imports are explicit. Full suite in one process: 1003 passed, 18 skipped.

### Chores

- Move .dockerignore back to the repository root
  ([`e07d310`](https://github.com/grenition/markdown-gost/commit/e07d3107a8f07d3b3dab5659d181f057bd20ec37))

Prefer the classic context-root ignore file over the BuildKit-only per-Dockerfile variant; works
  with any builder.

- Relocate .dockerignore to docker/Dockerfile.dockerignore
  ([`9b31721`](https://github.com/grenition/markdown-gost/commit/9b31721497df72885dd3da45636aa3652bba58f5))

BuildKit resolves the ignore file next to the Dockerfile itself (<dockerfile>.dockerignore), keeping
  the repository root clean. All build paths (local Docker 28, GitHub Actions buildx) are
  BuildKit-based.

- Ruff-fix screenshot test imports
  ([`dfe8928`](https://github.com/grenition/markdown-gost/commit/dfe892859744f359339d9f0fc7fbf734ed48d750))

- Slim the Dockerfile and move it to docker/
  ([`0a56357`](https://github.com/grenition/markdown-gost/commit/0a5635787cd0881f866d2b06bcdcfdc9eb949576))

- drop libreoffice-impress/-calc and make from the system layer (only core/writer/math are exercised
  by the rendering pipeline; the full pixel-diff screenshot gate re-verified rendering parity) - apt
  retry loop trimmed to 3 attempts; pandoc check simplified - test stage now chains from deps (one
  poetry install instead of two) - Dockerfile relocated to docker/Dockerfile; Makefile and CI
  workflows pass -f/--file accordingly

### Continuous Integration

- Draft GitHub Actions workflows
  ([`1c02f44`](https://github.com/grenition/markdown-gost/commit/1c02f44981a2227feb8092bdbb225f7241ef4b60))

- ci.yml: full suite (unit + integration + screenshot) inside the test image, MinIO sidecar for S3
  integration tests - publish.yml: on semver tag — GHCR runtime image + PyPI sdist/wheel via trusted
  publishing; immutable tags only, no floating latest

- Enforce conventional commits
  ([`caf3a66`](https://github.com/grenition/markdown-gost/commit/caf3a662bc209cccc059cb038b22aade8b7ac1f3))

Local commit-msg hook (.githooks, enabled by make install / make hooks) rejects non-conventional
  messages before the commit lands; CI re-checks every PR commit with the same script. Merge and
  revert commits are exempt. Required by semantic-release: the bump level is computed from commit
  types.

- **publish**: Fail when tag does not match pyproject version
  ([`b063909`](https://github.com/grenition/markdown-gost/commit/b06390988c1a2ed7f958fbc2165513ea45fdef43))

### Documentation

- Add AGENTS.md and an installable agent skill
  ([`bca5ef7`](https://github.com/grenition/markdown-gost/commit/bca5ef7ae7745ecca197e006615ae4dccb312229))

- AGENTS.md: short contributor rules — repo map, commands, contract-first syntax changes,
  screenshot-gate policy, brevity principle - skills/markdown-gost/: SKILL.md (CLI reference +
  syntax cheat sheet, Anthropic skill format; installable via npx skills add or copying into a
  harness skills directory) with syntax.md bundled - unit test keeps skills/markdown-gost/syntax.md
  identical to docs/syntax.md; test image copies skills/

- English README, syntax reference and architecture overview
  ([`9090918`](https://github.com/grenition/markdown-gost/commit/90909188fe9d09e57ea6bcadfea20387aaf4ec49))

- Merge syntax manifest and example corpus into single syntax.md
  ([`d944540`](https://github.com/grenition/markdown-gost/commit/d944540e9e790a0716d94c015175ec9d604bc91b))

One normative file instead of three: docs/syntax.md now carries the syntax contract (principles,
  attribute grammar, container roles, error rules, change protocol — translated from the Russian
  manifest) and the executable example corpus. The unit suite parses every fenced markdown block in
  the file (test_full_corpus), so documented constructs are proven to parse and a construct without
  a live example is not covered.

- docs/example.md and docs/syntax-manifest.md removed - reference docstrings updated to point at
  docs/syntax.md - the old English reference described the pre-migration syntax (%table, @cite:,
  ---content); the merged file documents the attribute-based syntax shipped since the manifest
  migration

- Reference the upcoming 0.2.0 image tag in the docker example
  ([`b0410a1`](https://github.com/grenition/markdown-gost/commit/b0410a1eb1f6ae4b434ba6cb6767035f76ca0c73))

- Single syntax source of truth in skills/markdown-gost/syntax.md
  ([`06acbf0`](https://github.com/grenition/markdown-gost/commit/06acbf0994b0de1f83a54945cf82ab03c164e016))

docs/syntax.md removed; the skill copy is now the only file. The corpus test, docstrings and doc
  links point at skills/markdown-gost/syntax.md; the docs-sync unit test is obsolete and deleted.

- Trim README to links and commands
  ([`33d9f9a`](https://github.com/grenition/markdown-gost/commit/33d9f9ac5af05fc9de8d74984cd9c276e03a0f6d))

- Validate import-syntax-mapping against the actual postprocessors
  ([`d399f1c`](https://github.com/grenition/markdown-gost/commit/d399f1c13285190943bc682cd6adf6190973d7fd))

The document described the pre-migration syntax and stale behavior. Fixed against code: captions
  fold into ': Caption' (not %table/%listing), unnumbered headings emit {.unnumbered} for a fixed H1
  title set, underline keeps the canonical [text]{.underline} form, monospace set gained DejaVu Sans
  Mono, image ids are sha256[:32] with content dedup, broken media links become ![](missing/{N})
  placeholders, semantic_docx prestep (style rename + math-table unfold) and PDF textbox recovery
  documented, dead ADR link removed, template names updated.

- **skill**: Drop stale docs/syntax.md reference
  ([`6425e6d`](https://github.com/grenition/markdown-gost/commit/6425e6d8d87943e24f317d61c12e1f5af0be675c))

### Features

- Agent skill
  ([`2fe75af`](https://github.com/grenition/markdown-gost/commit/2fe75afef9a47fb6b22a62b9867de06ae08c4870))

- Single multi-stage Docker image (CLI runtime + test stage)
  ([`e5fd4fc`](https://github.com/grenition/markdown-gost/commit/e5fd4fc4f184dd85c782d6d697a8b9539b47c60f))

base (python 3.13, LibreOffice, pinned pandoc, unoserver, fonts) -> deps -> test (dev deps +
  playwright, default CI target via --target) -> runtime (CLI entrypoint, non-root uid 10001,
  default build target). Entrypoint starts unoserver on loopback before exec'ing the CLI so 'convert
  --format pdf' works out of the box.

- **ci**: Automated semantic releases on push to main
  ([`20d1f6d`](https://github.com/grenition/markdown-gost/commit/20d1f6d2da20745a32cc2fa04068a5eed9addfdd))

python-semantic-release evaluates conventional commits on every push to main: feat -> minor,
  fix/perf -> patch, breaking changes (the "!" marker or footer) -> major

(major_on_zero). On release: version stamped into pyproject.toml and __version__, v-tag + GitHub
  release created, sdist/wheel published to PyPI via trusted publishing, runtime image pushed to
  GHCR with the same tag. Release commits carry [skip ci]. Test-image GHA cache scope shared between
  CI and publish gates. Tag-triggered publishing and the tag/version guard step are obsolete and
  removed.

- **templates**: Rename titlepage-mirea to titlepage-university, add logo param
  ([`9dc02b8`](https://github.com/grenition/markdown-gost/commit/9dc02b8412d2be9ea802007b2ccf273adfa789b1))

The bundled title page is a generic Russian university form and must not be tied to a particular
  institution.

- registry id: titlepage-university (module titlepage_university); the titlepage-* namespace stays
  free for institution-specific variants - new logo template param: local path or http(s) URL of the
  emblem image (~2.5 cm wide). A broken explicit reference raises; an absent logo renders no emblem.
  Preview layout gains logo_url - tests: logo render (local file), no-logo, broken-reference cases;
  corpus/manifest/preview fixtures moved to the new name - screenshot cases 14/14a/15g use the new
  template name; rendering is unchanged, baselines verified (75 passed) - known follow-up for the
  platform switch (Stage B): frontend template picker, titlepage block helper and default session
  markdown still reference the old name

### Refactoring

- Drop the bundled S3 storage backend from the library
  ([`c6da268`](https://github.com/grenition/markdown-gost/commit/c6da26800243e8d13cf5cff4ef09b874b0cafa83))

Object stores are an integrating-service concern, not a library one: the engine keeps the Storage
  protocol and the built-in FilesystemStorage, and services inject their own Storage implementations
  via the existing dependency-injection seams (convert/preview/import all accept a storage
  argument).

- storage/s3.py and the STORAGE_BACKEND=s3 branch removed; get_storage() is filesystem-only and
  points to injection for anything else - [s3] extra and boto3 dev dependency dropped - S3
  unit/integration tests moved out (hosted by the consuming service) - docs and CI no longer
  reference object storage or the EasyGOST platform; downstream integration details stay private


## v0.1.0 (2026-09-13)

### Features

- Port converter engine from md2gost@3cfc415 as markdown_gost
  ([`583e797`](https://github.com/grenition/markdown-gost/commit/583e79792870e3bd563fa52e9ca37508853e116d))

Engine snapshot (parser, renderables, DOCX renderer, HTML preview, DOCX/PDF import, storage, config
  presets, templates) with the HTTP API layer excluded — it lives in the EasyGOST platform
  converter-service now.

- package renamed md2gost -> markdown_gost (imports, CLI entry point, env prefixes MARKDOWN_GOST_*);
  output contracts preserved verbatim: HTML classes md2gost-*, Prometheus metric names md2gost_*,
  preview asset route prefix - optional dependencies: [pdf] unoserver tooling, [s3] boto3;
  prometheus_client replaced by metrics_compat no-op stand-ins when the metrics stack is not
  installed - titlepage-mirea template anonymized: university name/short name and bundled logo
  replaced with university_full/university_short params (default empty); baselines for cases 14,
  14a, 15g regenerated - engine-internal docs kept (syntax example, syntax manifest, import mapping,
  config reference)
