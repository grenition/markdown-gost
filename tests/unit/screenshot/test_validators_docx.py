"""Unit tests for the DOCX structural validator (Stage 1)."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import docx
import pytest


@pytest.fixture
def valid_docx(tmp_path: Path) -> Path:
    """Build a minimal but well-formed docx with python-docx."""
    out = tmp_path / "valid.docx"
    document = docx.Document()
    document.add_paragraph("hello world")
    document.save(str(out))
    return out


def test_validate_docx_returns_no_issues_for_valid_file(valid_docx: Path) -> None:
    from _validators.docx import validate_docx

    issues = validate_docx(valid_docx)
    assert issues == []


def test_validate_docx_reports_open_failure_on_corrupt_zip(tmp_path: Path) -> None:
    from _validators.docx import validate_docx

    bogus = tmp_path / "broken.docx"
    bogus.write_bytes(b"not a zip at all")

    issues = validate_docx(bogus)
    assert any(i.code == "docx.open_failed" and i.severity == "error" for i in issues)


def test_validate_docx_reports_xml_malformed_when_document_xml_corrupt(
    valid_docx: Path, tmp_path: Path
) -> None:
    from _validators.docx import validate_docx

    target = tmp_path / "malformed.docx"
    shutil.copy(valid_docx, target)

    # Replace word/document.xml with invalid XML.
    repacked = tmp_path / "malformed-repacked.docx"
    with (
        zipfile.ZipFile(target, "r") as zin,
        zipfile.ZipFile(repacked, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = b"<not-well-formed>>>"
            zout.writestr(item, data)

    issues = validate_docx(repacked)
    assert any(
        i.code == "docx.xml_malformed"
        and i.severity == "error"
        and i.location is not None
        and "word/document.xml" in i.location
        for i in issues
    )


def test_validate_docx_reports_broken_internal_relationship(
    valid_docx: Path, tmp_path: Path
) -> None:
    from _validators.docx import validate_docx

    repacked = tmp_path / "broken-rels.docx"
    bad_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rIdMissing" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        b'Target="media/does-not-exist.png"/>'
        b"</Relationships>"
    )
    with (
        zipfile.ZipFile(valid_docx, "r") as zin,
        zipfile.ZipFile(repacked, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                data = bad_rels
            zout.writestr(item, data)

    issues = validate_docx(repacked)
    assert any(i.code == "docx.rels.broken" and i.severity == "error" for i in issues)


def test_validate_docx_ignores_external_relationships(
    valid_docx: Path, tmp_path: Path
) -> None:
    from _validators.docx import validate_docx

    repacked = tmp_path / "external-rels.docx"
    external_rels = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rIdExt" '
        b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
        b'Target="https://example.com/" TargetMode="External"/>'
        b"</Relationships>"
    )
    with (
        zipfile.ZipFile(valid_docx, "r") as zin,
        zipfile.ZipFile(repacked, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                data = external_rels
            zout.writestr(item, data)

    issues = validate_docx(repacked)
    assert not any(i.code == "docx.rels.broken" for i in issues)
