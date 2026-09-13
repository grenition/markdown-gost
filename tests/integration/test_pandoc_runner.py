"""Integration test: real pandoc invocation against a minimal DOCX.

Skipped unless ``pandoc`` is available on PATH (or via ``PANDOC_BINARY``).
Exercises the full :class:`PandocRunner` happy path so we catch flag-name drift
between pandoc majors.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from markdown_gost.import_.pandoc_runner import DEFAULT_PANDOC_BINARY, PandocRunner

pytestmark = pytest.mark.requires_pandoc


def _pandoc_available() -> bool:
    import os

    binary = os.environ.get("PANDOC_BINARY", DEFAULT_PANDOC_BINARY)
    return shutil.which(binary) is not None


@pytest.fixture(autouse=True)
def _skip_if_no_pandoc() -> None:
    if not _pandoc_available():
        pytest.skip("pandoc is not installed; run inside docker image")


def _minimal_docx(path: Path) -> Path:
    """Build a tiny but valid .docx with one paragraph."""
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>hello pandoc</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    rels_ct = "application/vnd.openxmlformats-package.relationships+xml"
    doc_ct = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document.main+xml"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Default Extension="rels" ContentType="{rels_ct}"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/word/document.xml" ContentType="{doc_ct}"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return path


def test_run_produces_markdown_for_minimal_docx(tmp_path: Path) -> None:
    docx = _minimal_docx(tmp_path / "min.docx")
    media = tmp_path / "media"
    runner = PandocRunner()
    md = runner.run(docx, media)
    assert "hello pandoc" in md
    assert media.is_dir()
