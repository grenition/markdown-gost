"""Test harness for import golden tests (T038, T041).

A *case* is a directory under ``tests/import/golden/`` containing:

* ``input.docx`` **or** ``input.pdf`` — fixture file (committed; usually
  produced by an adjacent ``generate.py`` script). Per T041 the harness
  dispatches by extension via :func:`markdown_gost.import_.import_file`;
* ``expected.md`` — expected markdown output;
* ``expected_files/`` — optional directory listing the image file *names*
  the import is expected to emit (bytes are not compared, only names).

The harness imports the input through the full pipeline, compares the
resulting markdown to ``expected.md`` (allowing only semantically equivalent
list-marker and pipe-table padding from different Pandoc versions), and asserts the set of
emitted image names matches ``expected_files/``.

Set ``MARKDOWN_GOST_UPDATE_IMPORT_GOLDEN=1`` to overwrite ``expected.md`` and
``expected_files/`` from the current pipeline output. Per the project
workflow, regenerating baselines requires explicit user approval after
diffing the change.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path

from markdown_gost.core.parser import parse
from markdown_gost.import_ import ImportContext, ImportResult, import_file
from markdown_gost.storage import get_storage

_UPDATE_ENV = "MARKDOWN_GOST_UPDATE_IMPORT_GOLDEN"


@dataclass(frozen=True)
class GoldenCase:
    """A single fixture directory."""

    name: str
    case_dir: Path

    @property
    def input_docx(self) -> Path:
        return self.case_dir / "input.docx"

    @property
    def input_pdf(self) -> Path:
        return self.case_dir / "input.pdf"

    @property
    def input_path(self) -> Path:
        """The committed fixture; prefers ``input.pdf`` when present."""
        if self.input_pdf.is_file():
            return self.input_pdf
        return self.input_docx

    @property
    def is_pdf(self) -> bool:
        return self.input_pdf.is_file()

    @property
    def expected_md(self) -> Path:
        return self.case_dir / "expected.md"

    @property
    def expected_files_dir(self) -> Path:
        return self.case_dir / "expected_files"


def discover_cases(root: Path) -> list[GoldenCase]:
    """Find every subdirectory of ``root`` that has an input fixture."""
    cases: list[GoldenCase] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "input.docx").is_file() and not (child / "input.pdf").is_file():
            continue
        cases.append(GoldenCase(name=child.name, case_dir=child))
    return cases


def update_requested() -> bool:
    return os.environ.get(_UPDATE_ENV, "0").lower() in {"1", "true", "yes"}


def run_import_golden(case: GoldenCase, tmp_path: Path) -> None:
    """Run the pipeline for *case* and diff against expected.md.

    ``tmp_path`` is a writable directory provided by pytest where the
    pipeline drops extracted images (it becomes the ``images_dir`` for the
    :class:`ImportContext`).
    """
    images_dir = tmp_path / "imgs"
    storage = get_storage(default_base_dir=tmp_path)
    ctx = ImportContext(
        storage=storage,
        images_prefix=None,
        images_dir=images_dir,
    )

    result = import_file(case.input_path, ctx)

    actual_md = result.markdown
    actual_images = _image_names(images_dir)

    if update_requested():
        _write_baseline(case, actual_md, actual_images, images_dir)
        return

    _assert_markdown(case, actual_md)
    _assert_images(case, actual_images)


def _image_names(images_dir: Path) -> list[str]:
    if not images_dir.is_dir():
        return []
    return sorted(p.name for p in images_dir.iterdir() if p.is_file())


def _expected_image_names(case: GoldenCase) -> list[str]:
    if not case.expected_files_dir.is_dir():
        return []
    return sorted(p.name for p in case.expected_files_dir.iterdir() if p.is_file())


def _assert_markdown(case: GoldenCase, actual: str) -> None:
    if not case.expected_md.is_file():
        raise AssertionError(
            f"{case.name}: expected.md is missing. "
            f"Regenerate with {_UPDATE_ENV}=1 after auditing the output."
        )
    expected = case.expected_md.read_text(encoding="utf-8")
    if actual == expected or _padding_only_difference(expected, actual):
        return
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"{case.name}/expected.md",
            tofile=f"{case.name}/actual.md",
            n=3,
        )
    )
    raise AssertionError(f"markdown diverged from expected.md for case {case.name!r}:\n{diff}")


def _padding_only_difference(expected: str, actual: str) -> bool:
    """Whitelist layout differences AND require identical parsed structure.

    The structural check protects code fences, list indentation and continuation
    paragraphs. A general AST-only comparison would hide unsupported raw syntax;
    a whitespace-only comparison would hide meaningful changes inside code.
    """

    def normalize(text: str) -> str:
        lines = []
        for line in text.splitlines(keepends=True):
            line = re.sub(r"^([-+*]) {1,3}(?=\S)", r"\1 ", line)
            if line.startswith("|") and line.rstrip("\r\n").endswith("|"):
                line = re.sub(r"(?<=\|) +| +(?=\|)", "", line)
                line = re.sub(r"(?<=\|)(:?)---+(:?)(?=\|)", r"\1---\2", line)
            lines.append(line)
        return "".join(lines)

    if normalize(expected) != normalize(actual):
        return False

    def structure(value):
        if is_dataclass(value):
            return (
                type(value).__name__,
                tuple(
                    (field.name, structure(getattr(value, field.name)))
                    for field in fields(value)
                    if field.name not in {"node_id", "source_position"}
                ),
            )
        if isinstance(value, list):
            return [structure(item) for item in value]
        return value

    try:
        return structure(parse(expected)) == structure(parse(actual))
    except ValueError:
        return False


def _assert_images(case: GoldenCase, actual: list[str]) -> None:
    expected = _expected_image_names(case)
    if actual == expected:
        return
    raise AssertionError(
        f"image set diverged for case {case.name!r}: expected={expected}, actual={actual}"
    )


def _write_baseline(
    case: GoldenCase,
    actual_md: str,
    actual_image_names: list[str],
    images_dir: Path,
) -> None:
    case.expected_md.write_text(actual_md, encoding="utf-8")

    target = case.expected_files_dir
    if target.exists():
        shutil.rmtree(target)
    if not actual_image_names:
        return
    target.mkdir(parents=True)
    for name in actual_image_names:
        src = images_dir / name
        if src.is_file():
            shutil.copy2(src, target / name)


def import_for_inspection(case: GoldenCase, tmp_path: Path) -> ImportResult:
    """Run the pipeline without diffing — used by ad-hoc inspection scripts."""
    images_dir = tmp_path / "imgs"
    ctx = ImportContext(
        storage=get_storage(default_base_dir=tmp_path),
        images_prefix=None,
        images_dir=images_dir,
    )
    return import_file(case.input_path, ctx)


__all__ = [
    "GoldenCase",
    "discover_cases",
    "import_for_inspection",
    "run_import_golden",
    "update_requested",
]
