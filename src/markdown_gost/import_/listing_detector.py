"""Scan a DOCX for runs of monospace paragraphs (T035).

Pandoc does not turn monospace-fonted Word paragraphs into fenced code blocks
— it emits them as plain text with per-word ``code`` inlines. We pre-scan the
docx via ``python-docx`` to record where the code listings live, then the
:mod:`postprocessor.listing_wrapper` transformer wraps the matching markdown
lines in `` ``` ... ``` ``.

The detection is conservative: a paragraph counts as monospace only when
**every** non-empty run uses a recognised monospace typeface. Consecutive
monospace paragraphs are grouped into a single :class:`ParagraphRange`; the
first non-monospace or empty paragraph breaks the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from docx import Document

_MONOSPACE_FONTS = frozenset(
    {
        "Courier New",
        "Consolas",
        "Monaco",
        "Menlo",
        "Source Code Pro",
        "Liberation Mono",
        "DejaVu Sans Mono",
    }
)


@dataclass(frozen=True)
class ParagraphRange:
    """A contiguous run of monospace paragraphs in the docx body.

    ``start_index`` is the body-paragraph index of the first paragraph in the
    range; ``texts`` carries the literal text of each paragraph in order. The
    wrapper uses ``texts[0]`` and ``texts[-1]`` to locate the corresponding
    lines in the markdown emitted by pandoc.
    """

    start_index: int
    texts: tuple[str, ...]


def scan_monospace_paragraphs(docx_path: Path) -> list[ParagraphRange]:
    """Return monospace-paragraph runs in body order.

    Raises :class:`FileNotFoundError` if ``docx_path`` does not exist.
    """
    if not docx_path.is_file():
        raise FileNotFoundError(docx_path)

    document = Document(str(docx_path))
    ranges: list[ParagraphRange] = []
    current_start: int | None = None
    current_texts: list[str] = []

    for index, paragraph in enumerate(document.paragraphs):
        if _is_monospace_paragraph(paragraph):
            if current_start is None:
                current_start = index
            current_texts.append(paragraph.text)
            continue
        if current_start is not None:
            ranges.append(
                ParagraphRange(
                    start_index=current_start, texts=tuple(current_texts)
                )
            )
            current_start = None
            current_texts = []

    if current_start is not None:
        ranges.append(
            ParagraphRange(start_index=current_start, texts=tuple(current_texts))
        )

    return ranges


def _is_monospace_paragraph(paragraph: object) -> bool:
    runs = [run for run in paragraph.runs if run.text]  # type: ignore[attr-defined]
    if not runs:
        return False
    return all(run.font.name in _MONOSPACE_FONTS for run in runs)


__all__ = ["ParagraphRange", "scan_monospace_paragraphs"]
