"""Сборка пустого DOCX-документа на основе :class:`Config`.

Шаблон ``templates/base.docx`` даёт готовые ``Heading 1..9`` стили и связку
с ``numbering.xml`` (нумерация заголовков по-умолчанию). Поверх шаблона мы
точечно перетираем параметры из конфига — шрифт, поля, абзацный отступ,
выравнивание заголовков и т.д. — без хардкода под конкретный ГОСТ.
"""

from __future__ import annotations

from importlib import resources
from typing import IO, Any, cast

import docx
from docx.document import Document as DocxDocument
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_LINE_SPACING, WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Length, Pt, RGBColor

from markdown_gost.config.schema import Config, Font, HeadingLevel, PageSize
from markdown_gost.config.units import parse_length, parse_pt

_TEMPLATE_RESOURCE = "base.docx"
STRUCTURAL_HEADING_STYLE = "MD2GOST Structural Heading"

_PAGE_SIZES_PORTRAIT: dict[PageSize, tuple[Length, Length]] = {
    "A4": (parse_length("21cm"), parse_length("29.7cm")),
    "A3": (parse_length("29.7cm"), parse_length("42cm")),
    "Letter": (parse_length("8.5in"), parse_length("11in")),
}

_ALIGNMENT_MAP = {
    "left": WD_PARAGRAPH_ALIGNMENT.LEFT,
    "right": WD_PARAGRAPH_ALIGNMENT.RIGHT,
    "center": WD_PARAGRAPH_ALIGNMENT.CENTER,
    "justify": WD_PARAGRAPH_ALIGNMENT.JUSTIFY,
}


def _open_template() -> IO[bytes]:
    return resources.files("markdown_gost.templates").joinpath(_TEMPLATE_RESOURCE).open("rb")


def build_document(config: Config) -> DocxDocument:
    """Создать новый docx Document, готовый к рендеру по заданному конфигу."""

    with _open_template() as fp:
        document = docx.Document(fp)
    cast(Any, document)._body.clear_content()

    _apply_page(document, config)
    _apply_normal_style(document, config)
    _apply_heading_styles(document, config)
    return document


def _apply_page(document: DocxDocument, config: Config) -> None:
    section = document.sections[0]
    width, height = _PAGE_SIZES_PORTRAIT[config.page.size]
    if config.page.orientation == "landscape":
        width, height = height, width
    section.page_width = width
    section.page_height = height
    section.top_margin = parse_length(config.page.margins.top)
    section.bottom_margin = parse_length(config.page.margins.bottom)
    section.left_margin = parse_length(config.page.margins.left)
    section.right_margin = parse_length(config.page.margins.right)


def _apply_normal_style(document: DocxDocument, config: Config) -> None:
    style = cast(Any, document.styles["Normal"])
    style.font.name = config.font.family
    style.font.size = Pt(parse_pt(config.font.size))
    pf = style.paragraph_format
    pf.alignment = _ALIGNMENT_MAP[config.paragraph.alignment]
    pf.first_line_indent = parse_length(config.paragraph.indent_first_line)
    pf.line_spacing = config.font.line_spacing
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE


def _apply_heading_styles(document: DocxDocument, config: Config) -> None:
    for level in range(1, 7):
        style_name = f"Heading {level}"
        try:
            style = cast(Any, document.styles[style_name])
        except KeyError:
            continue
        spec = config.headings.levels.get(level) or HeadingLevel()
        _apply_heading_level(style, spec, default_font=config.font)
        if config.headings.numbering == "none":
            _strip_numbering(style)
    _apply_structural_heading_style(document, config)


def _apply_heading_level(style: Any, spec: HeadingLevel, *, default_font: Font) -> None:
    style.font.name = default_font.family or style.font.name
    if spec.size:
        style.font.size = Pt(parse_pt(spec.size))
    style.font.bold = spec.bold
    style.font.italic = spec.italic
    rpr = style.element.get_or_add_rPr()
    for existing in rpr.findall(qn("w:caps")):
        rpr.remove(existing)
    if spec.uppercase:
        # caps-эффект задаётся прямо в rPr.
        from lxml import etree

        caps = etree.SubElement(rpr, qn("w:caps"))
        caps.set(qn("w:val"), "true")
    pf = style.paragraph_format
    pf.alignment = _ALIGNMENT_MAP[spec.alignment]
    pf.space_before = parse_length(spec.space_before)
    pf.space_after = parse_length(spec.space_after)
    pf.page_break_before = spec.page_break_before
    pf.keep_with_next = spec.keep_with_next
    pf.first_line_indent = parse_length(spec.indent_first_line)
    style.font.color.rgb = RGBColor(0, 0, 0)


def _apply_structural_heading_style(document: DocxDocument, config: Config) -> None:
    try:
        style = cast(Any, document.styles[STRUCTURAL_HEADING_STYLE])
    except KeyError:
        style = cast(Any, document.styles.add_style(
            STRUCTURAL_HEADING_STYLE,
            WD_STYLE_TYPE.PARAGRAPH,
        ))
    style.base_style = document.styles["Normal"]
    _strip_numbering(style)
    _apply_heading_level(style, config.headings.structural, default_font=config.font)
    _strip_numbering(style)


def _strip_numbering(style: Any) -> None:
    ppr = style.element.find(qn("w:pPr"))
    if ppr is None:
        return
    for el in ppr.findall(qn("w:numPr")):
        ppr.remove(el)
