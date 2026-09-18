"""Unit tests for the full CLI (T020).

Covers ``convert``, ``validate``, ``--version``, ``--verbose``,
and the documented exit codes (0 ok, 1 user error, 2 system error).
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import markdown_gost
from markdown_gost.cli.__main__ import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Snapshot/restore the root logger because the CLI calls
    ``logging.basicConfig(force=True)`` and would otherwise leak between tests.
    """

    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


# --- --version --------------------------------------------------------------


@pytest.mark.parametrize("markdown", ["[](#missing)", "[@missing]"])
def test_validate_rejects_unresolved_references(runner, tmp_path, markdown):
    source = tmp_path / "input.md"
    source.write_text(markdown, encoding="utf-8")
    result = runner.invoke(cli, ["validate", str(source)])
    assert result.exit_code == 1
    assert "missing" in result.output


def test_version_flag_prints_package_version(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert markdown_gost.__version__ in result.stdout


# --- convert ---------------------------------------------------------------


def test_convert_writes_to_explicit_output(runner: CliRunner, tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hi\n", encoding="utf-8")
    out = tmp_path / "out.docx"

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"DOCX") as m:
        result = runner.invoke(cli, ["convert", str(md), "-o", str(out)])

    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"DOCX"
    assert m.call_args.kwargs["format"] == "docx"


def test_convert_default_output_uses_input_basename(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hi\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X"):
        result = runner.invoke(cli, ["convert", str(md)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "in.docx").exists()


def test_convert_pdf_format_invokes_pipeline(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "in.md"
    md.write_text("x", encoding="utf-8")
    out = tmp_path / "in.pdf"

    with patch(
        "markdown_gost.cli.__main__.convert_pipeline", return_value=b"%PDF-1.7\n"
    ) as m:
        result = runner.invoke(
            cli, ["convert", str(md), "--format", "pdf", "-o", str(out)]
        )

    assert result.exit_code == 0, result.output
    assert m.call_args.kwargs["format"] == "pdf"
    assert out.read_bytes().startswith(b"%PDF-")


def test_convert_html_format_is_rejected(runner: CliRunner, tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hi\n", encoding="utf-8")
    out = tmp_path / "in.html"

    result = runner.invoke(
        cli, ["convert", str(md), "--format", "html", "-o", str(out)]
    )

    assert result.exit_code != 0
    assert "html" in (result.stdout + result.stderr).lower()


def test_convert_uses_explicit_config(runner: CliRunner, tmp_path: Path) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hi\n", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("preset: gost-7-32-2017\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X") as m:
        result = runner.invoke(cli, ["convert", str(md), "--config", str(cfg)])

    assert result.exit_code == 0, result.output
    cfg_arg = m.call_args.kwargs.get("config") or m.call_args.args[1]
    assert cfg_arg.preset == "gost-7-32-2017"


def test_convert_unknown_preset_returns_user_error_exit_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "in.md"
    md.write_text("x", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("preset: nonexistent\n", encoding="utf-8")

    result = runner.invoke(cli, ["convert", str(md), "--config", str(cfg)])

    assert result.exit_code == 1, result.output
    assert "nonexistent" in (result.stdout + result.stderr).lower()


def test_convert_config_accepts_preset_name(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "in.md"
    md.write_text("# Hi\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X") as m:
        result = runner.invoke(
            cli, ["convert", str(md), "--config", "gost-7-32-2017"]
        )

    assert result.exit_code == 0, result.output
    cfg_arg = m.call_args.kwargs.get("config") or m.call_args.args[1]
    assert cfg_arg.preset == "gost-7-32-2017"


@pytest.mark.parametrize("command", ["convert", "validate"])
def test_config_unknown_name_lists_presets_exit_1(
    runner: CliRunner, tmp_path: Path, command: str
) -> None:
    md = tmp_path / "in.md"
    md.write_text("x", encoding="utf-8")

    result = runner.invoke(cli, [command, str(md), "--config", "nope"])

    assert result.exit_code == 1, result.output
    out = result.stdout + result.stderr
    assert "nope" in out
    assert "gost-7-32-2017" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("command", ["convert", "validate"])
def test_config_nonexistent_path_is_clean_user_error(
    runner: CliRunner, tmp_path: Path, command: str
) -> None:
    md = tmp_path / "in.md"
    md.write_text("x", encoding="utf-8")
    missing = tmp_path / "missing.yaml"

    result = runner.invoke(cli, [command, str(md), "--config", str(missing)])

    assert result.exit_code == 1, result.output
    out = result.stdout + result.stderr
    assert "missing.yaml" in out
    assert "Traceback" not in out


def test_convert_missing_input_returns_usage_error_exit_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(cli, ["convert", str(tmp_path / "missing.md")])
    assert result.exit_code == 2


def test_convert_pipeline_unexpected_error_returns_system_error_exit_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "in.md"
    md.write_text("x", encoding="utf-8")

    with patch(
        "markdown_gost.cli.__main__.convert_pipeline", side_effect=RuntimeError("boom")
    ):
        result = runner.invoke(cli, ["convert", str(md)])

    assert result.exit_code == 2, result.output
    assert "boom" in (result.stdout + result.stderr)


# --- validate -------------------------------------------------------------


def test_validate_succeeds_on_valid_md_and_default_preset(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n\nBody.\n", encoding="utf-8")

    result = runner.invoke(cli, ["validate", str(md)])

    assert result.exit_code == 0, result.output
    assert "ok" in result.stdout.lower()


def test_validate_unknown_preset_returns_exit_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("preset: doesnotexist\n", encoding="utf-8")

    result = runner.invoke(cli, ["validate", str(md), "--config", str(cfg)])

    assert result.exit_code == 1, result.output
    assert "doesnotexist" in (result.stdout + result.stderr).lower()


def test_validate_config_accepts_preset_name(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n\nBody.\n", encoding="utf-8")

    result = runner.invoke(cli, ["validate", str(md), "--config", "gost-7-32-2017"])

    assert result.exit_code == 0, result.output
    assert "preset=gost-7-32-2017" in result.stdout


def test_validate_invalid_config_field_returns_exit_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n", encoding="utf-8")
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "preset: gost-7-32-2017\noverrides:\n  font:\n    bogus_field: 1\n",
        encoding="utf-8",
    )

    result = runner.invoke(cli, ["validate", str(md), "--config", str(cfg)])

    assert result.exit_code == 1, result.output


def test_validate_missing_input_returns_exit_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(cli, ["validate", str(tmp_path / "missing.md")])
    assert result.exit_code == 2


# --- verbose --------------------------------------------------------------


def test_verbose_long_flag_enables_debug_logging(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X"):
        result = runner.invoke(cli, ["--verbose", "convert", str(md)])

    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.DEBUG


def test_verbose_short_flag_enables_debug_logging(
    runner: CliRunner, tmp_path: Path
) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X"):
        result = runner.invoke(cli, ["-v", "convert", str(md)])

    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.DEBUG


def test_default_log_level_is_info(runner: CliRunner, tmp_path: Path) -> None:
    md = tmp_path / "x.md"
    md.write_text("# Hi\n", encoding="utf-8")

    with patch("markdown_gost.cli.__main__.convert_pipeline", return_value=b"X"):
        result = runner.invoke(cli, ["convert", str(md)])

    assert result.exit_code == 0, result.output
    assert logging.getLogger().level == logging.INFO
