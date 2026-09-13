"""Reproducible fixture builder for 07-mixed-inline-formatting.

Stress-tests nested inline styles: bold-inside-italic, italic-inside-bold,
underline mixed with bold/italic, and underlined code-ish runs.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document

OUT = Path(__file__).parent / "input.docx"


def build() -> None:
    doc = Document()

    p1 = doc.add_paragraph()
    p1.add_run("Курсив с ")
    bold_in_italic = p1.add_run("жирным внутри")
    bold_in_italic.italic = True
    bold_in_italic.bold = True
    p1.add_run(" окружения.")

    p2 = doc.add_paragraph()
    p2.add_run("Подчёркнутый и ")
    bold_underline = p2.add_run("жирный + подчёркнутый")
    bold_underline.bold = True
    bold_underline.underline = True
    p2.add_run(" одновременно.")

    p3 = doc.add_paragraph()
    p3.add_run("Подчёркивание после ")
    underline_italic = p3.add_run("курсива с подчёркиванием")
    underline_italic.italic = True
    underline_italic.underline = True
    p3.add_run(".")

    p4 = doc.add_paragraph()
    p4.add_run("Все три стиля: ")
    all_three = p4.add_run("жирный курсив подчёркнутый")
    all_three.bold = True
    all_three.italic = True
    all_three.underline = True
    p4.add_run(".")

    doc.save(OUT)


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
