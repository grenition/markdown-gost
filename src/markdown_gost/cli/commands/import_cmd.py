"""``markdown-gost import`` — конвертация DOCX/PDF → расширенный markdown.

T036 ввёл docx-импорт; T041 добавил PDF через unoserver-prepass.

Exit codes:

* ``0`` — успех (даже если были fallbacks).
* ``1`` — невалидный вход: файл не найден или расширение не ``.docx`` / ``.pdf``.
* ``2`` — pandoc/unoserver упал на верхнем уровне.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import click

from markdown_gost.import_ import ImportContext, ImportResult, import_docx, import_pdf
from markdown_gost.import_.metrics import IMPORT_TOTAL
from markdown_gost.import_.pandoc_runner import PandocError
from markdown_gost.output.pdf_writer import UnoserverError
from markdown_gost.storage import get_storage

_LOGGER = logging.getLogger("markdown_gost.cli.import")

_HEADING_RE = re.compile(r"^#{1,6}\s")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _count_headings(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if _HEADING_RE.match(line))


def _count_tables(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if _TABLE_SEP_RE.match(line))


def _total_fallbacks(result: ImportResult) -> int:
    return sum(result.fallbacks.values())


@click.command("import")
@click.argument("input_path", metavar="INPUT", type=click.Path(path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output markdown path. Defaults to <input-stem>.md рядом с input.",
)
@click.option(
    "--images-dir",
    "images_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Куда класть извлечённые картинки. По умолчанию <output-stem>_files/.",
)
def import_command(
    input_path: Path,
    output: Path | None,
    images_dir: Path | None,
) -> None:
    """Импорт DOCX/PDF в расширенный markdown markdown_gost.

    PDF-input идёт через unoserver-prepass (PDF → DOCX → md). Сканированные
    PDF без текстового слоя возвращаются как пустой md без падения.
    """
    if not input_path.exists():
        click.echo(f"Error: input not found: {input_path}", err=True)
        sys.exit(1)

    suffix = input_path.suffix.lower()
    if suffix not in (".docx", ".pdf"):
        click.echo(
            f"Error: unsupported input extension {suffix!r}; expected .docx or .pdf",
            err=True,
        )
        sys.exit(1)

    if output is None:
        output = input_path.with_suffix(".md")
    if images_dir is None:
        images_dir = output.with_name(f"{output.stem}_files")

    storage = get_storage(default_base_dir=output.parent)
    ctx = ImportContext(
        storage=storage,
        images_prefix=None,
        images_dir=images_dir,
    )
    fmt_label = "pdf" if suffix == ".pdf" else "docx"

    _LOGGER.info(
        "import input=%s output=%s images_dir=%s format=%s",
        input_path,
        output,
        images_dir,
        fmt_label,
    )

    importer = import_pdf if suffix == ".pdf" else import_docx
    try:
        result = importer(input_path, ctx)
    except (PandocError, UnoserverError) as exc:
        IMPORT_TOTAL.labels(format=fmt_label, result="error").inc()
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.markdown, encoding="utf-8")

    if logging.getLogger().level <= logging.DEBUG and result.warnings:
        for warning in result.warnings:
            click.echo(f"warning: {warning}", err=True)

    fallback_total = _total_fallbacks(result)
    IMPORT_TOTAL.labels(format=fmt_label, result="success").inc()
    if fallback_total > 0:
        IMPORT_TOTAL.labels(format=fmt_label, result="fallback").inc()

    click.echo(
        "Imported: "
        f"{_count_headings(result.markdown)} headings, "
        f"{_count_tables(result.markdown)} tables, "
        f"{len(result.images)} images, "
        f"{fallback_total} fallbacks",
        err=True,
    )


__all__ = ["import_command"]
