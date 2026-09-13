"""Unit tests for ``markdown-gost import`` (T036).

Mock the ``import_docx`` pipeline so these tests are fast and don't need
pandoc on PATH. Exit-code behaviour comes straight from the task contract:

* ``0`` — success (even with fallbacks)
* ``1`` — bad input (missing file, unsupported extension)
* ``2`` — pandoc/unoserver top-level failure
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from markdown_gost.cli.__main__ import cli
from markdown_gost.import_ import ImportResult
from markdown_gost.import_.pandoc_runner import PandocError


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    root = logging.getLogger()
    saved_level = root.level
    saved_handlers = list(root.handlers)
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def _stub_import_result(markdown: str = "# H1\n\nbody\n") -> ImportResult:
    return ImportResult(markdown=markdown, images=[], warnings=[], fallbacks={})


def _make_docx(tmp_path: Path, name: str = "in.docx") -> Path:
    path = tmp_path / name
    path.write_bytes(b"PK\x03\x04 fake docx")
    return path


# --- success paths ---------------------------------------------------------


def test_import_writes_md_next_to_input_by_default(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    result_md = "# Title\n\nHello.\n"

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=_stub_import_result(result_md),
    ):
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 0, result.stderr
    out_md = tmp_path / "in.md"
    assert out_md.read_text(encoding="utf-8") == result_md


def test_import_writes_to_explicit_output(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    out = tmp_path / "sub" / "result.md"

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=_stub_import_result("ok\n"),
    ):
        result = runner.invoke(cli, ["import", str(docx), "-o", str(out)])

    assert result.exit_code == 0, result.stderr
    assert out.read_text(encoding="utf-8") == "ok\n"


def test_import_default_images_dir_is_output_stem_files(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=_stub_import_result(),
    ) as fake:
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 0, result.stderr
    ctx = fake.call_args.args[1]
    assert ctx.images_dir == tmp_path / "in_files"
    assert ctx.images_prefix is None


def test_import_explicit_images_dir_overrides_default(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    images = tmp_path / "media"

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=_stub_import_result(),
    ) as fake:
        result = runner.invoke(
            cli, ["import", str(docx), "--images-dir", str(images)]
        )

    assert result.exit_code == 0, result.stderr
    ctx = fake.call_args.args[1]
    assert ctx.images_dir == images


def test_import_summary_counts_headings_tables_images_fallbacks(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    markdown = (
        "# H1\n\n"
        "## H2\n\n"
        "Body.\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "| x | y |\n| --- | --- |\n| 3 | 4 |\n"
    )
    fake_result = ImportResult(
        markdown=markdown,
        images=[],
        warnings=[],
        fallbacks={"caption": 2, "image": 1},
    )

    # Use a non-empty images list via tuple shim
    fake_result.images.extend([])  # keep dataclass shape

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=fake_result,
    ):
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 0, result.stderr
    assert (
        "Imported: 2 headings, 2 tables, 0 images, 3 fallbacks" in result.stderr
    )


def test_import_exit_zero_with_fallbacks(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    fake_result = ImportResult(
        markdown="x\n", images=[], warnings=[], fallbacks={"listing": 5}
    )

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=fake_result,
    ):
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 0, result.stderr
    assert "5 fallbacks" in result.stderr


# --- exit code 1 ----------------------------------------------------------


def test_import_missing_input_returns_exit_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    missing = tmp_path / "nope.docx"
    result = runner.invoke(cli, ["import", str(missing)])
    assert result.exit_code == 1, result.stderr
    assert "not found" in result.stderr.lower()


def test_import_non_docx_returns_exit_1(
    runner: CliRunner, tmp_path: Path
) -> None:
    bogus = tmp_path / "in.txt"
    bogus.write_text("x", encoding="utf-8")
    result = runner.invoke(cli, ["import", str(bogus)])
    assert result.exit_code == 1, result.stderr
    assert ".docx" in result.stderr.lower()


def test_import_pdf_dispatches_to_import_pdf(
    runner: CliRunner, tmp_path: Path
) -> None:
    pdf = tmp_path / "in.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake\n")

    fake_result = SimpleNamespace(
        markdown="# H\n\nbody\n", images=[], warnings=[], fallbacks={}
    )
    with patch(
        "markdown_gost.cli.commands.import_cmd.import_pdf", return_value=fake_result
    ) as m:
        result = runner.invoke(cli, ["import", str(pdf)])
    assert result.exit_code == 0, result.stderr
    m.assert_called_once()
    out_md = tmp_path / "in.md"
    assert out_md.exists()
    assert "H" in out_md.read_text(encoding="utf-8")


# --- exit code 2 ----------------------------------------------------------


def test_import_pandoc_error_returns_exit_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        side_effect=PandocError("pandoc exploded"),
    ):
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 2, result.stderr
    assert "pandoc exploded" in result.stderr


# --- verbose / warnings ---------------------------------------------------


def test_warnings_not_printed_without_verbose(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    fake_result = ImportResult(
        markdown="x\n",
        images=[],
        warnings=["something noisy"],
        fallbacks={},
    )

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=fake_result,
    ):
        result = runner.invoke(cli, ["import", str(docx)])

    assert result.exit_code == 0, result.stderr
    assert "something noisy" not in result.stderr


def test_warnings_printed_when_verbose(
    runner: CliRunner, tmp_path: Path
) -> None:
    docx = _make_docx(tmp_path)
    fake_result = ImportResult(
        markdown="x\n",
        images=[],
        warnings=["something noisy"],
        fallbacks={},
    )

    with patch(
        "markdown_gost.cli.commands.import_cmd.import_docx",
        return_value=fake_result,
    ):
        result = runner.invoke(cli, ["-v", "import", str(docx)])

    assert result.exit_code == 0, result.stderr
    assert "something noisy" in result.stderr
