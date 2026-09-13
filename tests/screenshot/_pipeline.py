"""Screenshot test pipeline: case.md → docx (via CLI) → pdf (via unoserver) → page images.

Helper module — leading underscore keeps pytest from collecting it.
"""

from __future__ import annotations

import enum
import os
import socket
import subprocess
import sys
import xmlrpc.client
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pdf2image import convert_from_path
from PIL import Image

DEFAULT_TOLERANCE_PIXELS = 50
DEFAULT_DPI = 100

SCREENSHOT_ROOT = Path(__file__).parent
ARTIFACTS_DIR = SCREENSHOT_ROOT / "_artifacts"
REPORT_PDF = SCREENSHOT_ROOT / "_report.pdf"


class ValidationSeverity(str, enum.Enum):
    """Severity levels for a validation issue."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    """A single non-pixel-diff finding from a validator."""

    validator: str
    severity: ValidationSeverity
    code: str
    message: str
    location: str | None = None


@dataclass(frozen=True)
class CaseInputs:
    """A discovered screenshot case."""

    name: str
    case_dir: Path
    md_path: Path
    config_path: Path
    expected_pdf: Path
    tolerance_pixels: int
    dpi: int
    validate_docx: bool = True


@dataclass
class PageDiff:
    """Per-page comparison artifact paths."""

    index: int
    expected_path: Path
    actual_path: Path
    diff_path: Path
    pixels_differ: int


@dataclass
class CaseFailure:
    """Aggregated failure info for one case."""

    case: CaseInputs
    artifact_dir: Path
    pages: list[PageDiff] = field(default_factory=list)
    summary: str = ""
    validation_issues: list[ValidationIssue] = field(default_factory=list)


def has_blocking_issues(issues: list[ValidationIssue]) -> bool:
    """True if any issue is severity=error (warnings alone do not fail a case)."""
    return any(i.severity == ValidationSeverity.ERROR for i in issues)


class HarnessError(RuntimeError):
    """Pipeline error that should fail the test with a clear message."""


def is_unoserver_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def discover_cases(root: Path) -> list[CaseInputs]:
    """Find all subdirectories of `root` containing case.md."""
    cases: list[CaseInputs] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in {"__pycache__", "_artifacts"}:
            continue
        if child.name.startswith("."):
            continue
        if not (child / "case.md").exists():
            continue
        cases.append(_load_case(child))
    return cases


def _load_case(case_dir: Path) -> CaseInputs:
    md_path = case_dir / "case.md"
    config_path = case_dir / "config.yaml"
    expected_pdf = case_dir / "expected.pdf"

    if not config_path.exists():
        raise HarnessError(f"{case_dir.name}: missing config.yaml")

    meta_path = case_dir / "meta.yaml"
    tolerance = DEFAULT_TOLERANCE_PIXELS
    dpi = DEFAULT_DPI
    validate_docx = True
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        tolerance = int(meta.get("tolerance_pixels", tolerance))
        dpi = int(meta.get("dpi", dpi))
        validate_docx = bool(meta.get("validate_docx", validate_docx))

    return CaseInputs(
        name=case_dir.name,
        case_dir=case_dir,
        md_path=md_path,
        config_path=config_path,
        expected_pdf=expected_pdf,
        tolerance_pixels=tolerance,
        dpi=dpi,
        validate_docx=validate_docx,
    )


def run_md2gost_convert(md_path: Path, config_path: Path, out_docx: Path) -> None:
    """Invoke the CLI from T006 in a subprocess."""
    cmd = [
        sys.executable,
        "-m",
        "markdown_gost.cli",
        "convert",
        str(md_path),
        "-o",
        str(out_docx),
        "--config",
        str(config_path),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise HarnessError(
            "markdown-gost convert failed:\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stdout: {completed.stdout}\n"
            f"  stderr: {completed.stderr}"
        )
    if not out_docx.exists() or out_docx.stat().st_size == 0:
        raise HarnessError(f"markdown-gost convert produced empty output: {out_docx}")


def docx_to_pdf(
    docx_path: Path,
    pdf_path: Path,
    host: str,
    port: int,
) -> None:
    """Convert DOCX → PDF via unoserver XML-RPC."""
    proxy = xmlrpc.client.ServerProxy(
        f"http://{host}:{port}",
        allow_none=True,
    )
    indata = xmlrpc.client.Binary(docx_path.read_bytes())
    try:
        result = proxy.convert(None, indata, None, "pdf", None)
    except xmlrpc.client.Fault as fault:
        raise HarnessError(f"unoserver convert fault: {fault}") from fault
    if result is None:
        raise HarnessError("unoserver returned no data")
    pdf_bytes = result.data if isinstance(result, xmlrpc.client.Binary) else bytes(result)
    pdf_path.write_bytes(pdf_bytes)


def pdf_to_images(pdf_path: Path, dpi: int) -> list[Image.Image]:
    images = convert_from_path(str(pdf_path), dpi=dpi)
    return [img.convert("RGB") for img in images]


def unoserver_settings() -> tuple[str, int]:
    host = os.environ.get("UNOSERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("UNOSERVER_PORT", "2003"))
    return host, port


def update_baselines_enabled() -> bool:
    return os.environ.get("MARKDOWN_GOST_UPDATE_BASELINES", "").lower() in {"1", "true", "yes"}
