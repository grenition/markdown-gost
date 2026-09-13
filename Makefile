.PHONY: install hooks lint typecheck format test test-unit test-integration \
        test-screenshot test-html-calibration test-import-golden \
        test-import-roundtrip test-import-smoke import-golden-baseline \
        screenshot-baseline smoke build test-in-docker

# ---- local (poetry) ---------------------------------------------------------

hooks:
	git config core.hooksPath .githooks

install: hooks
	poetry install

lint:
	poetry run ruff check src tests

format:
	poetry run ruff format src tests
	poetry run ruff check --fix src tests

typecheck:
	poetry run mypy src

test: test-unit test-integration test-screenshot

test-unit:
	poetry run pytest tests/unit -v

test-integration:
	poetry run pytest tests/integration -v

test-screenshot:
	poetry run pytest tests/screenshot -v -rs

# Strict native HTML preview calibration against committed DOCX→PDF oracles.
# Unlike test-screenshot this retains artifacts for every compared page.
HTML_CALIBRATION_REFERENCE ?= tests/screenshot/html-calibration-reference.json
test-html-calibration:
	MARKDOWN_GOST_HTML_STRICT_RUNTIME=1 poetry run python tests/screenshot/html_calibration.py \
		--reference $(HTML_CALIBRATION_REFERENCE)

test-import-golden:
	poetry run pytest tests/import/golden -v

test-import-roundtrip:
	poetry run pytest tests/import/roundtrip -v

# Smoke: real "dirty" docx fixtures. Fixtures are NOT committed to git
# (see tests/import/smoke/README.md) — missing cases skip instead of failing.
test-import-smoke:
	poetry run pytest tests/import/smoke -v

# Regenerate expected.pdf for every screenshot case from the current pipeline
# output. Run only after a deliberate, verified rendering change. Commit the
# diff afterwards.
screenshot-baseline:
	MARKDOWN_GOST_UPDATE_BASELINES=1 poetry run pytest tests/screenshot -v

# Regenerate expected.md / expected_files for every import golden case.
# Run only after a deliberate, audited import-pipeline change.
import-golden-baseline:
	MARKDOWN_GOST_UPDATE_IMPORT_GOLDEN=1 poetry run pytest tests/import/golden -v

# ---- smoke ------------------------------------------------------------------

SMOKE_DIR := .smoke
SMOKE_INPUT := $(SMOKE_DIR)/smoke.md
SMOKE_OUTPUT := $(SMOKE_DIR)/smoke.docx

smoke:
	@mkdir -p $(SMOKE_DIR)
	@printf '# Smoke test\n\nMinimal paragraph for CLI skeleton.\n' > $(SMOKE_INPUT)
	@rm -f $(SMOKE_OUTPUT)
	poetry run markdown-gost convert $(SMOKE_INPUT) -o $(SMOKE_OUTPUT)
	@test -s $(SMOKE_OUTPUT) || { echo "smoke: output $(SMOKE_OUTPUT) is missing or empty"; exit 1; }
	@echo "smoke: OK -> $(SMOKE_OUTPUT)"

# ---- docker ------------------------------------------------------------------

IMAGE ?= markdown-gost:local
TEST_IMAGE ?= markdown-gost:test

build:
	docker build -f docker/Dockerfile -t $(IMAGE) .

# Full test suite inside the test image: the entrypoint starts unoserver
# (LibreOffice) before pytest, so integration and screenshot tests run
# against the same rendering stack that ships to production.
test-in-docker:
	docker build -f docker/Dockerfile --target test -t $(TEST_IMAGE) .
	docker run --rm $(TEST_IMAGE)
