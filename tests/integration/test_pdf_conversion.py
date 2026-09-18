"""End-to-end PDF conversion against a live unoserver (T018).

Runs only inside the docker-compose stack where ``unoserver`` is reachable on
``UNOSERVER_HOST``/``UNOSERVER_PORT``. Skipped on hosts where unoserver is not
running so ``make test-integration`` stays usable on developer machines that
intentionally don't install LibreOffice.
"""

from __future__ import annotations

import io

import pytest

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.convert import convert
from markdown_gost.output.pdf_writer import (
    convert_to_pdf,
    ping_unoserver,
)

pytestmark = pytest.mark.requires_unoserver

SAMPLE_MD = (
    "# Заголовок\n\n"
    "Это первый абзац для проверки конвертации DOCX → PDF.\n\n"
    "## Подзаголовок\n\nВторой абзац, тоже непустой.\n"
)


def _config():
    return load_config_from_string("preset: gost-7-32-2017\n")


@pytest.fixture(autouse=True)
def _skip_if_unoserver_unreachable() -> None:
    if not ping_unoserver():
        pytest.skip("unoserver is not reachable; run inside docker-compose stack")


def _docx_bytes_from_markdown(markdown: str) -> bytes:
    return convert(markdown, _config(), format="docx")


def test_convert_to_pdf_returns_pdf_signature() -> None:
    docx = _docx_bytes_from_markdown(SAMPLE_MD)
    pdf = convert_to_pdf(docx)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000  # any non-empty real document is at least ~kB


def test_convert_to_pdf_yields_at_least_one_page() -> None:
    pdf2image = pytest.importorskip("pdf2image")
    docx = _docx_bytes_from_markdown(SAMPLE_MD)
    pdf = convert_to_pdf(docx)
    images = pdf2image.convert_from_bytes(pdf, dpi=72)
    assert len(images) >= 1


def test_convert_pipeline_pdf_format_matches_writer() -> None:
    pdf_via_pipeline = convert(SAMPLE_MD, _config(), format="pdf")
    assert pdf_via_pipeline.startswith(b"%PDF-")


def test_convert_to_pdf_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        convert_to_pdf(b"")


# Defensive: keep io import live (used by future fixtures).
assert io is not None
