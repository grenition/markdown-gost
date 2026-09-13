"""End-to-end CLI tests (T020).

Spawn ``python -m markdown_gost.cli ...`` as a subprocess so the console entry point
is exercised the same way users invoke it. PDF case is skipped when unoserver
is not reachable so the suite still runs on developer machines without
LibreOffice.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SAMPLE_MD = "# Заголовок\n\nПервый абзац.\n\n## Подзаголовок\n\nВторой абзац.\n"


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "markdown_gost.cli", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def test_cli_module_runnable_version(tmp_path: Path) -> None:
    result = _run_cli("--version", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "0.1.0" in result.stdout


def test_convert_real_md_to_docx(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")

    result = _run_cli("convert", str(md), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    out = tmp_path / "doc.docx"
    assert out.exists()
    assert out.stat().st_size > 0


def test_convert_default_output_path(tmp_path: Path) -> None:
    md = tmp_path / "named.md"
    md.write_text("# Hello\n", encoding="utf-8")

    result = _run_cli("convert", str(md), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "named.docx").exists()


def test_convert_real_md_to_pdf_via_unoserver(tmp_path: Path) -> None:
    from markdown_gost.output.pdf_writer import ping_unoserver

    if not ping_unoserver():
        pytest.skip("unoserver is not reachable; run inside docker-compose stack")

    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    out = tmp_path / "doc.pdf"

    result = _run_cli(
        "convert", str(md), "--format", "pdf", "-o", str(out), cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF-")


def test_validate_real_md_ok(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")

    result = _run_cli("validate", str(md), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_validate_unknown_preset_exits_1(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# A\n", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("preset: nope\n", encoding="utf-8")

    result = _run_cli("validate", str(md), "--config", str(cfg), cwd=tmp_path)

    assert result.returncode == 1, result.stderr


def test_missing_input_exits_2(tmp_path: Path) -> None:
    result = _run_cli("convert", str(tmp_path / "missing.md"), cwd=tmp_path)
    assert result.returncode == 2
