from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import cache, cached_property
from inspect import ismethod
from math import ceil
from typing import Any, cast

from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Length, Pt
from docx.styles.style import _ParagraphStyle
from docx.text.font import Font as DocxFont
from docx.text.paragraph import Paragraph
from docx.text.parfmt import ParagraphFormat
from docx.text.run import Run
from freetype import Face  # type: ignore[import-untyped]
from PIL import Image, ImageDraw, ImageFont

# Calibration overrides: ``freetype`` reports a slightly different line height
# from what Word actually uses for the listed font/size combinations. Adding
# new entries is a deliberate, reviewable action — far better than ad-hoc
# branches scattered through the code.
_LINE_HEIGHT_CALIBRATION: dict[tuple[str, int], float] = {
    # font-name substring (case-sensitive), point size -> exact line height in pt
    ("Times", 14): 16.05,
    ("Courier", 12): 13.61,
}


@cache
def find_font(name: str, bold: bool, italic: bool) -> str:
    """Return the absolute path to a font matching name/bold/italic.

    Uses ``fc-list`` (available on Linux and macOS via fontconfig). Raises
    :class:`ValueError` if no match is found or the font name is empty.
    """
    if not name:
        raise ValueError("Invalid font name")

    fc_list = shutil.which("fc-list")
    if fc_list is None:
        raise RuntimeError("fc-list (fontconfig) is required for font lookup but was not found")

    result = subprocess.run([fc_list], check=True, capture_output=True, text=True)
    fonts = [line.split(":") for line in result.stdout.strip().split("\n")]
    fonts = [font for font in fonts if len(font) == 3]

    def _style_matches(styles: str, want_bold: bool, want_italic: bool) -> bool:
        # "Oblique" is the upright-slanted form used by several free fonts
        # (DejaVu Sans Mono, Liberation Mono) where MS-fonts would say
        # "Italic". For width/line-height measurement they're interchangeable.
        has_italic = "Italic" in styles or "Oblique" in styles
        return ("Bold" in styles) == bool(want_bold) and has_italic == bool(want_italic)

    for path, names, styles in fonts:
        if name in names and _style_matches(styles, bold, italic):
            return path

    # Если конкретный font не найден (например, Arial на Linux-контейнере без
    # MS-fonts), fallback на ближайший по характеру:
    #   - моноширинные → DejaVu Sans Mono / Courier;
    #   - sans-serif → Liberation Sans (metrically совпадает с Arial) / DejaVu Sans;
    #   - остальные (serif) → Times New Roman / Liberation Serif / DejaVu Serif.
    # Метрики поплывут на пару процентов, но layout не упадёт; sans/serif-разделение
    # критично для table row-height в Docker, где Arial → DejaVu Serif давал перебор
    # ~7% против реальной высоты, которую LO считает по Liberation Sans.
    fallback_candidates: list[str]
    lname = name.lower()
    monospace_hints = ("mono", "consolas", "courier", "menlo", "fira", "source code")
    sans_hints = ("arial", "helvetica", "verdana", "tahoma", "calibri", "segoe", "sans")
    if any(hint in lname for hint in monospace_hints):
        fallback_candidates = ["DejaVu Sans Mono", "Courier New", "Courier", "Menlo"]
    elif any(hint in lname for hint in sans_hints):
        fallback_candidates = ["Liberation Sans", "DejaVu Sans", "Arial"]
    else:
        fallback_candidates = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]

    for fallback in fallback_candidates:
        if fallback == name:
            continue
        for path, names, styles in fonts:
            if fallback in names and _style_matches(styles, bold, italic):
                return path

    raise ValueError(f"Font {name!r} (bold={bold}, italic={italic}) not found")


def _safe_getmembers(obj: Any) -> list[tuple[str, Any]]:
    """Like ``inspect.getmembers`` but ignores attributes that raise on access.

    Some python-docx properties (e.g. ``Font.part`` on detached fonts) raise
    ``ValueError`` instead of ``AttributeError``; ``getmembers`` does not
    handle that, so we replicate it manually.
    """
    members: list[tuple[str, Any]] = []
    for name in dir(obj):
        try:
            value = getattr(obj, name)
        except (AttributeError, ValueError):
            continue
        members.append((name, value))
    return members


def _merge_objects(*objects: Any) -> Any:
    """Return a new object whose attributes are the right-most non-None values.

    Used to flatten the style inheritance chain (default style -> base styles
    -> paragraph style -> direct formatting) into a single attribute lookup.
    """

    class MergedObject:
        pass

    merged = MergedObject()
    for name, value in _safe_getmembers(objects[0]):
        if name.startswith("_") or ismethod(value):
            continue
        setattr(merged, name, value)

    for obj in objects[1:]:
        for name, value in _safe_getmembers(obj):
            if name.startswith("_") or ismethod(value):
                continue
            if value is not None:
                setattr(merged, name, value)
    return merged


class Font:
    """Thin wrapper over PIL.ImageFont + freetype.Face for text measurement."""

    def __init__(self, name: str, bold: bool, italic: bool, size_pt: int) -> None:
        path = find_font(name, bold, italic)
        self._pil_font = ImageFont.truetype(path, size_pt)
        self._draw = ImageDraw.Draw(Image.new("RGB", (1000, 1000)))

        self._face = Face(path)
        self._face.set_char_size(int(size_pt * 64))
        self._size_pt = size_pt

    def get_text_width(self, text: str) -> Length:
        if not self.is_mono:
            bbox = self._draw.textbbox((0, 0), text, self._pil_font)
            return Pt(bbox[2] - bbox[0])
        # for monospaced fonts, PIL textbbox under-reports — compute by hand
        return Pt(len(text) * self._face.glyph.advance.x / 64)

    def get_line_height(self) -> Length:
        family_raw = self._face.family_name or b""
        family = family_raw.decode("utf-8", errors="ignore")
        for substring, size_pt in _LINE_HEIGHT_CALIBRATION:
            if substring in family and self._size_pt == size_pt:
                return Pt(_LINE_HEIGHT_CALIBRATION[(substring, size_pt)])
        return Pt(self._face.size.height / 64)

    @cached_property
    def is_mono(self) -> bool:
        self._face.load_char("i")
        i_width = self._face.glyph.advance.x
        self._face.load_char("m")
        return bool(i_width == self._face.glyph.advance.x)


@dataclass
class ParagraphSizerResult:
    before: Length
    lines: int
    line_height: Length
    line_spacing: float
    after: Length

    @property
    def base(self) -> Length:
        return Length(
            int(self.before + ((self.lines - 1) * self.line_spacing + 1) * self.line_height)
        )

    @property
    def full(self) -> Length:
        return Length(
            int(self.before + self.line_height * self.line_spacing * self.lines + self.after)
        )


# XPath-friendly tag name for a w:r run element (used to walk through the
# paragraph XML directly — paragraph.runs misses runs inside hyperlinks).
_RUN_TAG = qn("w:r")


class ParagraphSizer:
    """Estimates the rendered height of a paragraph before docx commits it."""

    def __init__(
        self,
        paragraph: Paragraph,
        previous_paragraph: Paragraph | None,
        max_width: Length,
    ) -> None:
        self.paragraph = paragraph
        self.previous_paragraph = previous_paragraph
        self.max_width = max_width
        self.same_style_as_previous = (
            paragraph.style == previous_paragraph.style if previous_paragraph is not None else False
        )

    @cached_property
    def _default_style(self) -> _ParagraphStyle:
        # Build a stand-in element exposing rPr/pPr from the document defaults.
        # python-docx's _ParagraphStyle constructor only reads these two
        # attributes, so a duck-typed object is enough.
        styles_element = self.paragraph.part.document.styles.element  # type: ignore[attr-defined]
        rpr = styles_element.xpath("w:docDefaults/w:rPrDefault/w:rPr")[0]
        ppr = styles_element.xpath("w:docDefaults/w:pPrDefault/w:pPr")[0]

        class _DefaultStyleElement:
            pass

        default_style_element = _DefaultStyleElement()
        default_style_element.rPr = rpr  # type: ignore[attr-defined]
        default_style_element.pPr = ppr  # type: ignore[attr-defined]
        return _ParagraphStyle(cast(Any, default_style_element))

    @cached_property
    def _styles(self) -> list[_ParagraphStyle]:
        styles: list[_ParagraphStyle] = [cast(_ParagraphStyle, self.paragraph.style)]
        while styles[-1].base_style:
            styles.append(cast(_ParagraphStyle, styles[-1].base_style))
        styles.append(self._default_style)
        return styles

    @cached_property
    def _is_contextual_spacing(self) -> bool:
        ppr_elements = [self.paragraph.paragraph_format._element.pPr] + [
            style._element.pPr for style in self._styles
        ]
        return any(ppr is not None and ppr.xpath("./w:contextualSpacing") for ppr in ppr_elements)

    def count_lines(
        self,
        runs: list[Run],
        max_width: Length,
        docx_font: DocxFont,
        first_line_indent: Length,
        is_mono: bool = False,
    ) -> int:
        lines = 1
        line_width: float = float(first_line_indent)

        space_width: float = float(
            Font(
                docx_font.name or "",
                bool(docx_font.bold),
                bool(docx_font.italic),
                int(cast(Any, docx_font.size).pt),
            ).get_text_width(" ")
        )
        if not is_mono:
            space_width *= 0.81

        word_part = ""
        word_parts_widths: list[float] = [0]
        spaces = 0
        for i, run in enumerate(runs):
            if word_part:
                word_part = ""
                word_parts_widths.append(0)

            run_docx_font = _merge_objects(docx_font, run.font)
            font = Font(
                run_docx_font.name,
                bool(run_docx_font.bold),
                bool(run_docx_font.italic),
                int(run_docx_font.size.pt),
            )

            run_text = run.text
            if run_text == "" and run._element.xpath("w:noBreakHyphen"):
                run_text = "-"
            if i == len(runs) - 1:
                # appended space forces the last word to flush through the
                # measurement loop (the loop only commits a word on space)
                run_text += " "

            for c in run_text:
                if c == " ":
                    if any(word_parts_widths):
                        width = spaces * space_width + sum(word_parts_widths)
                        if width <= max_width - line_width:
                            line_width += width
                        elif width > max_width - first_line_indent:
                            if lines == 1 and line_width == first_line_indent and not spaces:
                                lines += ceil((width - (max_width - first_line_indent)) / max_width)
                                line_width = (width - (max_width - first_line_indent)) % max_width
                            else:
                                lines += ceil(width / max_width)
                                line_width = width % max_width
                        else:
                            lines += 1
                            line_width = sum(word_parts_widths)

                        word_part = ""
                        word_parts_widths = [0]
                        spaces = 1
                    else:
                        spaces += 1
                else:
                    word_part += c
                    word_parts_widths[-1] = float(font.get_text_width(word_part))

        return int(lines)

    def calculate_height(self) -> ParagraphSizerResult:
        max_width = self.max_width

        docx_font: DocxFont = _merge_objects(
            *[style.font for style in self._styles[::-1] if style.font],
            cast(Any, self.paragraph.style).font,
        )

        paragraph_format: ParagraphFormat = _merge_objects(
            *[style.paragraph_format for style in self._styles[::-1] if style.paragraph_format],
            self.paragraph.paragraph_format,
        )

        max_width = Length(
            int(
                max_width
                - (paragraph_format.left_indent or 0)
                - (paragraph_format.right_indent or 0)
            )
        )

        font = Font(
            docx_font.name or "",
            bool(docx_font.bold),
            bool(docx_font.italic),
            int(cast(Any, docx_font.size).pt),
        )

        # python-docx's paragraph.runs misses runs nested inside hyperlinks etc.;
        # walking w:r elements directly is the only reliable way.
        runs: list[Run] = [
            Run(cast(Any, element), self.paragraph)
            for element in self.paragraph._element.iter(_RUN_TAG)
        ]

        lines = self.count_lines(
            runs,
            max_width,
            docx_font,
            Length(int(paragraph_format.first_line_indent or 0)),
            font.is_mono,
        )

        previous_paragraph_format: ParagraphFormat | None = None
        if self.previous_paragraph is not None:
            previous_paragraph_styles: list[_ParagraphStyle] = [
                cast(_ParagraphStyle, self.previous_paragraph.style)
            ]
            while previous_paragraph_styles[-1].base_style:
                previous_paragraph_styles.append(
                    cast(_ParagraphStyle, previous_paragraph_styles[-1].base_style)
                )
            previous_paragraph_styles.append(self._default_style)
            previous_paragraph_format = _merge_objects(
                *[
                    style.paragraph_format
                    for style in previous_paragraph_styles[::-1]
                    if style.paragraph_format
                ],
                self.previous_paragraph.paragraph_format,
            )

        if self._is_contextual_spacing and self.same_style_as_previous:
            assert previous_paragraph_format is not None
            before = Length(int(previous_paragraph_format.space_after or 0))
        else:
            before = Length(int(paragraph_format.space_before or 0))
            if previous_paragraph_format is not None:
                before = Length(max(0, int(before - (previous_paragraph_format.space_after or 0))))

        after = Length(int(paragraph_format.space_after or 0))

        line_height = font.get_line_height()
        line_spacing: float = float(paragraph_format.line_spacing or 1.0)
        if paragraph_format.line_spacing_rule == WD_LINE_SPACING.EXACTLY:
            line_spacing = line_spacing / float(line_height)
        elif paragraph_format.line_spacing_rule == WD_LINE_SPACING.AT_LEAST:
            raise NotImplementedError("Line spacing rule AT_LEAST is not supported")

        return ParagraphSizerResult(before, lines, line_height, line_spacing, after)
