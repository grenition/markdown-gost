"""DOCX/PDF → markdown-gost markdown import pipeline (ADR-0006).

Package is named ``import_`` because ``import`` is a Python keyword.
"""

from __future__ import annotations

from .pandoc_runner import PandocError, PandocRunner
from .pipeline import import_docx, import_file, import_pdf
from .result import ImageRef, ImportContext, ImportResult

__all__ = [
    "ImageRef",
    "ImportContext",
    "ImportResult",
    "PandocError",
    "PandocRunner",
    "import_docx",
    "import_file",
    "import_pdf",
]
