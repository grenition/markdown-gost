"""Reproducible fixture builder for 02-headings.

Manually-numbered headings (``1 Введение``) plus a non-numbered
``СОДЕРЖАНИЕ`` section — the import postprocessor must keep both shapes
intact.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

OUT = Path(__file__).parent / "input.docx"


def build() -> None:
    doc = Document()

    doc.add_heading("СОДЕРЖАНИЕ", level=1)
    doc.add_paragraph("Введение")
    doc.add_paragraph("1 Анализ требований")
    doc.add_paragraph("1.1 Сценарии использования")

    doc.add_heading("Введение", level=1)
    doc.add_paragraph("Вступительный текст работы.")

    doc.add_heading("1 Анализ требований", level=1)
    doc.add_paragraph("Краткое описание раздела.")

    doc.add_heading("1.1 Функциональные требования", level=2)
    doc.add_paragraph("Текст подраздела.")

    doc.add_heading("1.1.1 Регистрация пользователя", level=3)
    doc.add_paragraph("Детализированный текст.")

    doc.save(OUT)


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
