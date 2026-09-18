"""meta.yaml fields gating per-case validators."""

from __future__ import annotations

from pathlib import Path


def _write_case(case_dir: Path, meta: str | None) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.md").write_text("# hi\n", encoding="utf-8")
    (case_dir / "config.yaml").write_text("preset: gost-7-32-2017\n", encoding="utf-8")
    (case_dir / "expected.pdf").write_bytes(b"%PDF-1.4 stub")
    if meta is not None:
        (case_dir / "meta.yaml").write_text(meta, encoding="utf-8")


def test_load_case_defaults_validation_flags_true(tmp_path: Path) -> None:
    from _pipeline import _load_case  # type: ignore[attr-defined]

    case_dir = tmp_path / "01-default"
    _write_case(case_dir, meta=None)

    case = _load_case(case_dir)
    assert case.validate_docx is True


def test_load_case_respects_meta_disable_flags(tmp_path: Path) -> None:
    from _pipeline import _load_case  # type: ignore[attr-defined]

    case_dir = tmp_path / "02-disabled"
    _write_case(case_dir, meta="validate_docx: false\n")

    case = _load_case(case_dir)
    assert case.validate_docx is False
