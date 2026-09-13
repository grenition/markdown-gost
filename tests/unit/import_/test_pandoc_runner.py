"""Unit tests for :class:`markdown_gost.import_.pandoc_runner.PandocRunner`.

The runner is a thin subprocess wrapper. We mock ``subprocess.run`` and verify
that we invoke the right binary with the flags fixed by
``docs/import-syntax-mapping.md`` §1 and that errors / timeouts surface as
:class:`PandocError`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from markdown_gost.import_.pandoc_runner import (
    DEFAULT_PANDOC_BINARY,
    DEFAULT_TIMEOUT_SECONDS,
    PandocError,
    PandocRunner,
)


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def test_run_invokes_configured_binary_with_required_flags(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    media = tmp_path / "media"

    runner = PandocRunner()
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.return_value = _completed(stdout="# hi\n")
        markdown = runner.run(docx, media)

    assert markdown == "# hi\n"
    run.assert_called_once()
    cmd: list[str] = run.call_args.args[0]
    assert cmd[0] == DEFAULT_PANDOC_BINARY
    assert str(docx) in cmd
    assert "--from=docx" in cmd
    to_flag = next(c for c in cmd if c.startswith("--to="))
    expected_to_bits = {
        "markdown_strict",
        "pipe_tables",
        "backtick_code_blocks",
        "tex_math_dollars",
        "raw_tex",
        "bracketed_spans",
    }
    assert expected_to_bits.issubset(set(to_flag.removeprefix("--to=").split("+")))
    assert f"--extract-media={media}" in cmd
    assert "--wrap=none" in cmd
    kwargs = run.call_args.kwargs
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert kwargs["timeout"] == DEFAULT_TIMEOUT_SECONDS


def test_run_respects_env_binary_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANDOC_BINARY", "/usr/local/bin/pandoc-3")
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    runner = PandocRunner()
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.return_value = _completed(stdout="")
        runner.run(docx, tmp_path / "media")
    assert run.call_args.args[0][0] == "/usr/local/bin/pandoc-3"


def test_run_respects_env_timeout_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANDOC_TIMEOUT_SECONDS", "5")
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    runner = PandocRunner()
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.return_value = _completed(stdout="")
        runner.run(docx, tmp_path / "media")
    assert run.call_args.kwargs["timeout"] == 5


def test_run_raises_on_nonzero_exit(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    runner = PandocRunner()
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.return_value = _completed(stdout="", stderr="bad zip", returncode=2)
        with pytest.raises(PandocError) as info:
            runner.run(docx, tmp_path / "media")
    assert "bad zip" in str(info.value)


def test_run_raises_on_timeout(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    runner = PandocRunner(timeout_seconds=1)
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.side_effect = subprocess.TimeoutExpired(cmd="pandoc", timeout=1)
        with pytest.raises(PandocError) as info:
            runner.run(docx, tmp_path / "media")
    assert "timed out" in str(info.value).lower()


def test_run_raises_when_input_missing(tmp_path: Path) -> None:
    runner = PandocRunner()
    with pytest.raises(PandocError):
        runner.run(tmp_path / "nope.docx", tmp_path / "media")


def test_run_creates_media_dir_when_missing(tmp_path: Path) -> None:
    docx = tmp_path / "in.docx"
    docx.write_bytes(b"PK\x03\x04")
    media = tmp_path / "deep" / "media"
    runner = PandocRunner()
    with mock.patch("markdown_gost.import_.pandoc_runner.subprocess.run") as run:
        run.return_value = _completed(stdout="")
        runner.run(docx, media)
    assert media.is_dir()
