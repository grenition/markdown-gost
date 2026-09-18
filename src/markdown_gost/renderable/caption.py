"""Подпись для нумерованного объекта (картинка / таблица / листинг).

Используется renderable'ами после или перед самим объектом. Стиль берётся
из ``config.captions.<category>``; формат — из поля ``format`` со
строковыми placeholder'ами ``{category}`` / ``{number}`` / ``{text}``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Length
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import CaptionStyle, Config
from markdown_gost.config.units import parse_length
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.paragraph_sizer import ParagraphSizer
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable

# Локализованные подписи. ГОСТ — русский; пресет может это переопределить через
# format-строку, если потребуется другой язык.
_CATEGORY_LABELS: dict[str, str] = {
    "image": "Рисунок",
    "table": "Таблица",
    "listing": "Листинг",
}

_ALIGNMENT_MAP = {
    "left": WD_PARAGRAPH_ALIGNMENT.LEFT,
    "right": WD_PARAGRAPH_ALIGNMENT.RIGHT,
    "center": WD_PARAGRAPH_ALIGNMENT.CENTER,
    "justify": WD_PARAGRAPH_ALIGNMENT.JUSTIFY,
}


class Caption(Renderable):
    """Однострочная (или многострочная) подпись.

    ``before=True`` — подпись располагается перед объектом (таблицы/листинги),
    тогда при недостатке места внизу страницы переносится вместе с объектом.
    Для картинок ``before=False`` — подпись идёт после.
    """

    def __init__(
        self,
        parent: Any,
        config: Config,
        *,
        category: str,
        number: int | str,
        text: str | None,
        before: bool = False,
    ) -> None:
        self._parent = parent
        self._config = config
        self._category = category
        self._before = before
        self._spec: CaptionStyle = self._select_style(config, category)

        self._docx_paragraph = DocxParagraph(create_element("w:p"), parent)
        self._docx_paragraph.alignment = _ALIGNMENT_MAP[self._spec.alignment]
        pf = self._docx_paragraph.paragraph_format
        pf.first_line_indent = 0
        # Подпись над объектом (таблица/листинг) не отрывается от его первой
        # строки при разрыве страницы (w:keepNext).
        if self._before:
            pf.keep_with_next = True
        # T013b: spacing берём из CaptionStyle. Дефолт ``"0pt"`` сохраняет
        # старое поведение. Для caption-ов *перед* блоком (table) Table-
        # renderable дополнительно накладывает ``table.space_before`` поверх —
        # последнее присваивание выигрывает.
        pf.space_before = parse_length(self._spec.space_before)
        pf.space_after = parse_length(self._spec.space_after)
        if self._spec.line_spacing is not None:
            pf.line_spacing = self._spec.line_spacing

        label = _CATEGORY_LABELS.get(category, category.capitalize())
        formatted = self._format_text(label=label, number=number, text=text)
        run = self._docx_paragraph.add_run(formatted)
        if self._spec.italic:
            run.italic = True
        if self._spec.bold:
            run.bold = True

    @property
    def docx_paragraph(self) -> DocxParagraph:
        return self._docx_paragraph

    @staticmethod
    def _select_style(config: Config, category: str) -> CaptionStyle:
        captions = config.captions
        spec = getattr(captions, category, None)
        if isinstance(spec, CaptionStyle):
            return spec
        return CaptionStyle()

    def _format_text(self, *, label: str, number: int | str, text: str | None) -> str:
        try:
            formatted = self._spec.format.format(
                category=label, number=number, text=text or ""
            )
        except (KeyError, IndexError):
            formatted = f"{label} {number}"
            if text:
                formatted = f"{formatted} — {text}"
            return formatted
        if not text:
            # Format обычно содержит дефис/тире и хвостовой плейсхолдер. Если
            # подписи нет — подчищаем «висячий» сепаратор.
            formatted = formatted.rstrip()
            for trailing in (" —", " -", "—", "-"):
                if formatted.endswith(trailing):
                    formatted = formatted[: -len(trailing)].rstrip()
                    break
        return formatted

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        previous_docx_paragraph: DocxParagraph | None = None
        if previous_rendered is not None and isinstance(
            previous_rendered.docx_element, DocxParagraph
        ):
            previous_docx_paragraph = previous_rendered.docx_element

        height_data = ParagraphSizer(
            self._docx_paragraph,
            previous_docx_paragraph,
            layout_state.max_width,
        ).calculate_height()

        # Если подпись стоит ПЕРЕД объектом и место заканчивается — двигаемся
        # на следующую страницу, чтобы не оставить «голую» подпись внизу.
        if self._before and (
            (height_data.lines + 2 - 1) * height_data.line_spacing + 1
        ) * height_data.line_height > layout_state.remaining_page_height:
            self._docx_paragraph.paragraph_format.page_break_before = True
            height_data = ParagraphSizer(
                self._docx_paragraph,
                None,
                layout_state.max_width,
            ).calculate_height()

        height = height_data.full
        if self._docx_paragraph.paragraph_format.page_break_before:
            height = Length(int(height) + int(layout_state.remaining_page_height))

        yield RenderedInfo(self._docx_paragraph, Length(int(height)))
