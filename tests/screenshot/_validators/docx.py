"""DOCX structural validator (Stage 1).

Checks structural correctness of a generated .docx:

1. The file opens via ``python-docx`` (catches deeply broken packages).
2. Every XML part under ``word/`` is well-formed (lxml parse).
3. Every internal relationship target resolves to an existing zip entry.
4. Optional OOXML XSD validation behind ``MARKDOWN_GOST_DOCX_XSD=1``. If the
   bundle is unavailable, a single ``severity=warning`` issue is emitted —
   we never fail a case purely on missing XSDs.

The validator is a pure function: input is a path, output is a list of
``ValidationIssue`` objects. No side effects beyond reading the file.
"""

from __future__ import annotations

import os
import posixpath
import zipfile
from pathlib import Path

import docx
from _pipeline import ValidationIssue, ValidationSeverity
from lxml import etree

_RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_RELATIONSHIP_TAG = f"{{{_RELS_NS}}}Relationship"


def validate_docx(path: Path) -> list[ValidationIssue]:
    """Return a list of structural issues for the docx at ``path``."""
    issues: list[ValidationIssue] = []

    # 1. python-docx open
    try:
        docx.Document(str(path))
    except Exception as exc:  # any failure here is a defect we want surfaced
        issues.append(
            ValidationIssue(
                validator="docx",
                severity=ValidationSeverity.ERROR,
                code="docx.open_failed",
                message=f"python-docx could not open the file: {exc}",
                location=str(path.name),
            )
        )
        # If python-docx can't open it, the zip may also be unreadable below.

    # 2-3. zip-level checks. Try zip; if it fails, emit open_failed too.
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
            issues.extend(_check_xml_parts(zf, names))
            issues.extend(_check_relationships(zf, names))
    except zipfile.BadZipFile as exc:
        if not any(i.code == "docx.open_failed" for i in issues):
            issues.append(
                ValidationIssue(
                    validator="docx",
                    severity=ValidationSeverity.ERROR,
                    code="docx.open_failed",
                    message=f"not a valid zip archive: {exc}",
                    location=str(path.name),
                )
            )
        return issues

    # 4. optional XSD validation
    if os.environ.get("MARKDOWN_GOST_DOCX_XSD", "").lower() in {"1", "true", "yes"}:
        issues.extend(_xsd_validate_or_warn())

    return issues


def _check_xml_parts(zf: zipfile.ZipFile, names: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    xml_parts = [n for n in names if n.startswith("word/") and n.endswith((".xml", ".rels"))]
    for part_name in xml_parts:
        try:
            etree.fromstring(zf.read(part_name))
        except etree.XMLSyntaxError as exc:
            issues.append(
                ValidationIssue(
                    validator="docx",
                    severity=ValidationSeverity.ERROR,
                    code="docx.xml_malformed",
                    message=f"XML parse error: {exc}",
                    location=part_name,
                )
            )
    return issues


def _check_relationships(zf: zipfile.ZipFile, names: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    rels_parts = [
        n for n in names if n.endswith(".rels") and ("_rels/" in n)
    ]
    for rels_name in rels_parts:
        try:
            tree = etree.fromstring(zf.read(rels_name))
        except etree.XMLSyntaxError:
            # Already reported by _check_xml_parts when applicable.
            continue
        # Determine the directory the relationships are anchored in.
        # Rule: "<dir>/_rels/<name>.rels" anchors at "<dir>/".
        # ".rels" files at the package root ("_rels/.rels") anchor at "".
        anchor = _rels_anchor_dir(rels_name)
        for rel in tree.iter(_RELATIONSHIP_TAG):
            target_mode = rel.get("TargetMode", "Internal")
            if target_mode == "External":
                continue
            target = rel.get("Target", "")
            if not target:
                continue
            resolved = _resolve_target(anchor, target)
            if resolved is None:
                continue
            if resolved not in names:
                issues.append(
                    ValidationIssue(
                        validator="docx",
                        severity=ValidationSeverity.ERROR,
                        code="docx.rels.broken",
                        message=(
                            f"relationship Id={rel.get('Id', '?')} -> '{target}' "
                            f"resolves to '{resolved}' which is not in the package"
                        ),
                        location=rels_name,
                    )
                )
    return issues


def _rels_anchor_dir(rels_name: str) -> str:
    """Return the package-relative directory that this .rels file anchors to.

    For ``word/_rels/document.xml.rels`` the anchor is ``word/``.
    For ``_rels/.rels`` the anchor is ``""`` (package root).
    """
    parts = rels_name.split("/")
    # Drop trailing ["_rels", "<name>.rels"]
    if len(parts) >= 2 and parts[-2] == "_rels":
        parts = parts[:-2]
    if not parts:
        return ""
    return "/".join(parts) + "/"


def _resolve_target(anchor: str, target: str) -> str | None:
    """Resolve a relationship Target relative to its anchor dir.

    Absolute targets (starting with ``/``) are taken from the package root.
    Returns ``None`` for unresolvable / out-of-package targets.
    """
    resolved = (
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.normpath(anchor + target)
    )
    if resolved.startswith("../") or resolved == "..":
        return None
    return resolved


def _xsd_validate_or_warn() -> list[ValidationIssue]:
    """Optional XSD branch — emits a warning if XSDs aren't bundled.

    Stage 1 deliberately keeps this minimal: we don't ship XSDs in-repo, so
    the realistic outcome is the warning. A future iteration can plug in a
    real schema bundle without changing the call site.
    """
    return [
        ValidationIssue(
            validator="docx",
            severity=ValidationSeverity.WARNING,
            code="docx.xsd.unavailable",
            message=(
                "MARKDOWN_GOST_DOCX_XSD=1 is set but the OOXML XSD bundle is not available; "
                "skipping schema validation."
            ),
            location=None,
        )
    ]
