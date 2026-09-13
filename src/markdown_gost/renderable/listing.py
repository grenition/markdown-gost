"""Рендер листингов кода (T014).

Структура: подпись «Листинг N — ...» + 1×1 таблица без видимых границ,
внутри которой каждая строка кода — отдельный параграф моноширинным шрифтом.

Два режима, переключение через тогглер ``config.captions.continuation_break``
(общий для таблиц и листингов):

* **manual** (``true``) — наш собственный page-break: измеряем высоту каждой
  строки ParagraphSizer'ом, на стыке страниц выводим один ``<w:tbl>`` и
  параграф «Продолжение листинга N» с ``page_break_before``, далее новый
  ``<w:tbl>``.
* **native** (``false``, default) — собираем один сплошной ``<w:tbl>`` с одной
  ячейкой, содержащей все строки. Word/LO переносят контент строки между
  страницами автоматически (без вставки подписи продолжения).

Подсветка: ``config.listing.syntax_highlighting`` включает pygments. Стиль —
``sas`` (как в legacy-рендере). Неизвестный язык / ``language is None`` —
монохром, исключение pygments не валит рендер.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from copy import copy
from typing import Any, cast

from docx.document import Document as DocxDocument
from docx.enum.text import WD_LINE_SPACING, WD_PARAGRAPH_ALIGNMENT
from docx.shared import Length, Pt, RGBColor
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length, parse_pt
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.paragraph_sizer import ParagraphSizer
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import (
    Renderable,
    RenderedInfo,
    RequiresNumbering,
    SubRenderable,
)
from markdown_gost.renderable.caption import Caption

_log = logging.getLogger(__name__)

# Внутренние отступы ячейки. Минимальные — листинг должен быть «прижат» к
# рамке таблицы, чтобы не выглядеть как отдельный блок с воздухом вокруг.
_CELL_PAD_TOP_DXA = 40
_CELL_PAD_LEFT_DXA = 80
_CELL_PAD_BOTTOM_DXA = 40
_CELL_PAD_RIGHT_DXA = 80

# Толщина бордера в восьмых долях точки. ``"4"`` = 0.5pt.
_BORDER_SIZE_EIGHTHS = "4"
_BORDER_COLOR = "000000"


class Listing(Renderable, RequiresNumbering):
    """Листинг кода с (опциональной) подписью и подсветкой.

    Если ``caption_text`` равен ``None`` (исходник без подписи),
    рендерится «голая» кодовая коробка без подписи и без участия в нумерации
    листингов: ``numbering_category`` обнуляется, чтобы Renderer не дёргал
    счётчик. Рендер при этом остаётся тем же — таблица 1×1 с моноширными
    параграфами в ячейке.
    """

    numbering_category = "listing"

    def __init__(
        self,
        parent: DocxDocument,
        config: Config,
        node: ast.Listing,
        *,
        caption_text: str | None = None,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._caption_text = caption_text
        self._number: int | str | None = None

        # Блок без подписи — не нумеруется.
        # Опт-аут от RequiresNumbering: пустая категория → Renderer
        # пропускает вызов numberer'а.
        self._emit_caption = caption_text is not None
        if not self._emit_caption:
            self.numbering_category = ""

        # Manual-режим включён, когда поднят тогглер captions.continuation_break
        # и сам листинг получает caption. Блок без подписи или
        # выключенный тогглер — рендерим один <w:tbl> и отдаём разрез Word'у.
        self._continuation_enabled = (
            config.captions.continuation_break and self._emit_caption
        )

        self._line_paragraphs: list[DocxParagraph] = self._build_line_paragraphs()

    def set_number(self, number: int | str) -> None:
        self._number = number

    @property
    def caption_text(self) -> str | None:
        """Текст подписи листинга (без префикса «Листинг N — »)."""

        return self._caption_text

    # ------------------------------------------------------------------
    # построение параграфов строк
    # ------------------------------------------------------------------

    def _build_line_paragraphs(self) -> list[DocxParagraph]:
        """Преобразовать ``code`` в список параграфов-строк.

        В режиме подсветки используем pygments: токенизируем исходник,
        формируем runs со стилями. При исключении (неизвестный язык,
        отсутствие pygments) — fallback на монохром.
        """

        text = (self._node.code or "").rstrip("\n")
        if not text:
            text = ""
        lines = text.split("\n") if text else [""]

        if (
            self._config.listing.syntax_highlighting
            and self._node.language
        ):
            highlighted = self._build_highlighted_paragraphs(text)
            if highlighted is not None:
                return highlighted

        return [self._build_plain_paragraph(line) for line in lines]

    def _build_plain_paragraph(self, line: str) -> DocxParagraph:
        p = self._new_line_paragraph()
        run = p.add_run(line)
        self._apply_listing_font(run)
        return p

    def _build_highlighted_paragraphs(self, text: str) -> list[DocxParagraph] | None:
        try:
            from pygments import lex
            from pygments.lexers import get_lexer_by_name
            from pygments.styles import get_style_by_name
            from pygments.util import ClassNotFound
        except ImportError:  # pragma: no cover — pygments в обязательных зависимостях
            _log.warning("pygments not installed; listing rendered monochrome")
            return None

        try:
            lexer = get_lexer_by_name(self._node.language or "")
        except ClassNotFound:
            _log.info(
                "pygments: unknown language %r, listing rendered monochrome",
                self._node.language,
            )
            return None

        try:
            style = get_style_by_name("sas")
        except ClassNotFound:  # pragma: no cover — стиль встроен в pygments
            return None

        token_styles = {token: style.style_for_token(token) for token, _ in style}

        paragraphs: list[DocxParagraph] = [self._new_line_paragraph()]
        for ttype, value in lex(text, lexer):
            ts = token_styles.get(ttype) or {}
            # Pygments идёт по mro для неизвестных подтипов — на всякий случай
            # подымаемся вверх по дереву и ищем ближайшего предка.
            current = ttype
            while not ts and current.parent is not None:
                current = current.parent
                ts = token_styles.get(current) or ts
            chunks = value.split("\n")
            for idx, chunk in enumerate(chunks):
                if chunk:
                    run = paragraphs[-1].add_run(chunk)
                    self._apply_listing_font(run)
                    self._apply_token_style(run, ts)
                if idx < len(chunks) - 1:
                    paragraphs.append(self._new_line_paragraph())
        # Завершающий пустой параграф (последний "\n" в исходнике обычно
        # уже снят в _build_line_paragraphs, но в highlighted-ветке мы получаем
        # текст до rstrip — оставляем как есть).
        return paragraphs

    @staticmethod
    def _apply_token_style(run: Any, ts: dict[str, Any]) -> None:
        if not ts:
            return
        if ts.get("bold"):
            run.bold = True
        if ts.get("italic"):
            run.italic = True
        color = ts.get("color")
        if color:
            try:
                run.font.color.rgb = RGBColor.from_string(color)
            except (ValueError, TypeError):
                _log.debug("pygments: bad color %r ignored", color)

    def _new_line_paragraph(self) -> DocxParagraph:
        p = DocxParagraph(create_element("w:p"), self._parent)
        pf = p.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = 0
        pf.space_after = 0
        pf.line_spacing = self._config.listing.line_spacing
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
        return p

    def _apply_listing_font(self, run: Any) -> None:
        run.font.name = self._config.listing.font.family
        run.font.size = Pt(parse_pt(self._config.listing.font.size))

    # ------------------------------------------------------------------
    # построение таблицы-обёртки
    # ------------------------------------------------------------------

    def _content_dxa(self) -> int:
        section = self._parent.sections[0]
        page_w: Length = section.page_width or Length(0)
        left_m: Length = section.left_margin or Length(0)
        right_m: Length = section.right_margin or Length(0)
        content_emu = int(page_w) - int(left_m) - int(right_m)
        return int(round(content_emu / 914400 * 1440))

    def _build_table_shell(self) -> Any:
        """Построить ``<w:tbl>`` с одной ячейкой и невидимыми границами.

        Содержимое ячейки добавляется отдельно (см. :meth:`_assemble_table`).
        """

        content_dxa = self._content_dxa()
        tbl = create_element("w:tbl")

        tbl_pr = create_element("w:tblPr")
        tbl_pr.append(
            create_element("w:tblW", {"w:w": str(content_dxa), "w:type": "dxa"})
        )
        tbl_pr.append(create_element("w:tblLayout", {"w:type": "fixed"}))
        # Все границы — single 0.5pt чёрный. Строгая «коробка» вокруг кода
        # — академическая практика; цвет/толщина пока не конфигурируются.
        borders_children = []
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders_children.append(
                create_element(
                    f"w:{side}",
                    {
                        "w:val": "single",
                        "w:sz": _BORDER_SIZE_EIGHTHS,
                        "w:space": "0",
                        "w:color": _BORDER_COLOR,
                    },
                )
            )
        tbl_pr.append(create_element("w:tblBorders", borders_children))
        tbl_pr.append(
            create_element(
                "w:tblCellMar",
                [
                    create_element(
                        "w:top", {"w:w": str(_CELL_PAD_TOP_DXA), "w:type": "dxa"}
                    ),
                    create_element(
                        "w:left", {"w:w": str(_CELL_PAD_LEFT_DXA), "w:type": "dxa"}
                    ),
                    create_element(
                        "w:bottom",
                        {"w:w": str(_CELL_PAD_BOTTOM_DXA), "w:type": "dxa"},
                    ),
                    create_element(
                        "w:right",
                        {"w:w": str(_CELL_PAD_RIGHT_DXA), "w:type": "dxa"},
                    ),
                ],
            )
        )
        tbl.append(tbl_pr)

        tbl_grid = create_element("w:tblGrid")
        tbl_grid.append(create_element("w:gridCol", {"w:w": str(content_dxa)}))
        tbl.append(tbl_grid)

        return tbl

    def _assemble_table(self, paragraphs: list[DocxParagraph]) -> DocxTable:
        """Собрать ``<w:tbl>`` 1×1, в ячейке которого лежат ``paragraphs``.

        Параграфы переиспользуются «как есть» — каждый параграф принадлежит
        ровно одной таблице, поэтому копировать их не нужно (в отличие от
        ``Table``-renderable, где xml-строки кешируются и копируются между
        чанками — здесь у нас единый владелец).
        """

        tbl = self._build_table_shell()
        tr = create_element("w:tr")
        # cantSplit на строке листинга НЕ ставим: в native-режиме нам нужно,
        # чтобы Word сам ломал содержимое ячейки между страницами; в manual-
        # режиме — каждый chunk сам по себе помещается на странице, а если
        # вдруг что-то выйдет за границу из-за расхождения оценки и реальной
        # вёрстки LO — лучше пусть строка ляжет на следующую страницу, чем
        # пропадёт за рамками страницы.
        tc = create_element("w:tc")
        tc_pr = create_element(
            "w:tcPr",
            [
                create_element(
                    "w:tcW", {"w:w": str(self._content_dxa()), "w:type": "dxa"}
                )
            ],
        )
        tc.append(tc_pr)
        for p in paragraphs:
            tc.append(p._p)
        tr.append(tc)
        tbl.append(tr)
        return DocxTable(tbl, cast(Any, self._parent))

    # ------------------------------------------------------------------
    # измерение
    # ------------------------------------------------------------------

    def _measure_paragraph_height(self, paragraph: DocxParagraph) -> Length:
        inner_dxa = max(
            0, self._content_dxa() - _CELL_PAD_LEFT_DXA - _CELL_PAD_RIGHT_DXA
        )
        inner_emu = int(inner_dxa * 914400 / 1440)
        try:
            result = ParagraphSizer(
                paragraph, None, Length(inner_emu)
            ).calculate_height()
        except (ValueError, RuntimeError) as exc:
            _log.debug("ParagraphSizer failed for listing line: %s", exc)
            font_pt = parse_pt(self._config.listing.font.size)
            return Length(int(Pt(font_pt * self._config.listing.line_spacing)))
        return Length(int(result.full))

    def _table_overhead(self) -> Length:
        cell_pad_emu = int(
            (_CELL_PAD_TOP_DXA + _CELL_PAD_BOTTOM_DXA) * 914400 / 1440
        )
        # Аддитивный запас на бордеры (см. table.py / T013a).
        border_safety = int(Pt(1.5))
        return Length(cell_pad_emu + border_safety)

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        if self._emit_caption:
            # Подпись перед листингом — стандарт для блочных нумерованных
            # объектов с подписью «сверху» (Caption сам сдвинется на новую
            # страницу, если в конце страницы не осталось места).
            caption = Caption(
                self._parent,
                self._config,
                category="listing",
                number=self._number or 0,
                text=self._caption_text,
                before=True,
            )
            # listing.space_before накладывается поверх captions.listing.space_before
            # (последнее присваивание выигрывает) — единая ментальная модель
            # «отступ блока», как у таблицы (см. T013b).
            listing_space_before_emu = int(
                parse_length(self._config.listing.space_before)
            )
            if listing_space_before_emu > 0:
                caption.docx_paragraph.paragraph_format.space_before = Length(
                    listing_space_before_emu
                )

            last_caption_info: RenderedInfo | None = None
            for item in caption.render(previous_rendered, copy(layout_state)):
                if isinstance(item, RenderedInfo):
                    last_caption_info = item
                yield item
            if last_caption_info is not None:
                layout_state.add_height(last_caption_info.height)

        if self._continuation_enabled:
            yield from self._render_manual(layout_state)
        else:
            yield from self._render_native(layout_state)

        yield from self._emit_trailing_spacer(layout_state)

    def _render_native(
        self, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        line_heights = [
            int(self._measure_paragraph_height(p)) for p in self._line_paragraphs
        ]
        total_height = sum(line_heights, 0) + int(self._table_overhead())
        tbl = self._assemble_table(self._line_paragraphs)
        yield RenderedInfo(tbl, Length(total_height))
        layout_state.add_height(Length(total_height))

    def _render_manual(
        self, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        overhead = int(self._table_overhead())
        chunk_paragraphs: list[DocxParagraph] = []
        chunk_height = overhead

        def flush_chunk() -> Generator[RenderedInfo | SubRenderable]:
            nonlocal chunk_paragraphs, chunk_height
            if not chunk_paragraphs:
                return
            tbl = self._assemble_table(chunk_paragraphs)
            yield RenderedInfo(tbl, Length(chunk_height))
            layout_state.add_height(Length(chunk_height))
            chunk_paragraphs = []
            chunk_height = overhead

        for paragraph in self._line_paragraphs:
            line_height = int(self._measure_paragraph_height(paragraph))
            remaining = int(layout_state.remaining_page_height)
            # Если строка не помещается в текущий chunk на этой странице и
            # chunk уже непустой — флешим и продолжаем на новой странице с
            # подписью «Продолжение листинга N».
            if chunk_paragraphs and chunk_height + line_height > remaining:
                yield from flush_chunk()
                cont_para, cont_h = self._build_continuation(layout_state)
                yield RenderedInfo(cont_para, cont_h)
                layout_state.add_height(cont_h)
            chunk_paragraphs.append(paragraph)
            chunk_height += line_height

        yield from flush_chunk()

    def _build_continuation(
        self, layout_state: LayoutState
    ) -> tuple[DocxParagraph, Length]:
        """Параграф «Продолжение листинга N» с ``page_break_before``.

        ``space_before`` берётся из ``captions.listing.space_before`` — Word
        применяет его и поверх page-break, поэтому подпись продолжения
        получает такой же воздух сверху, как обычная подпись листинга.
        """

        spec = self._config.captions.listing
        text = f"Продолжение листинга {self._number or 0}"

        para = DocxParagraph(create_element("w:p"), self._parent)
        pf = para.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = Length(int(parse_length(spec.space_before)))
        pf.space_after = 0
        pf.page_break_before = True

        align_map = {
            "left": WD_PARAGRAPH_ALIGNMENT.LEFT,
            "right": WD_PARAGRAPH_ALIGNMENT.RIGHT,
            "center": WD_PARAGRAPH_ALIGNMENT.CENTER,
            "justify": WD_PARAGRAPH_ALIGNMENT.JUSTIFY,
        }
        para.alignment = align_map.get(spec.alignment, WD_PARAGRAPH_ALIGNMENT.LEFT)
        run = para.add_run(text)
        if spec.italic:
            run.italic = True
        if spec.bold:
            run.bold = True

        sizer_height = ParagraphSizer(
            para, None, layout_state.max_width
        ).calculate_height()
        full_height = int(sizer_height.full) + int(layout_state.remaining_page_height)
        return para, Length(full_height)

    def _emit_trailing_spacer(
        self, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        """Trailing spacer-параграф после листинга (см. T013b для таблиц)."""

        space_after_emu = int(parse_length(self._config.listing.space_after))
        if space_after_emu <= 0:
            return
        space_dxa = int(round(space_after_emu / 914400 * 1440))
        spacer = DocxParagraph(create_element("w:p"), self._parent)
        p_pr = create_element(
            "w:pPr",
            [
                create_element(
                    "w:spacing",
                    {
                        "w:before": str(space_dxa),
                        "w:after": "0",
                        "w:line": "20",
                        "w:lineRule": "exact",
                    },
                ),
                create_element("w:ind", {"w:firstLine": "0"}),
            ],
        )
        spacer._p.insert(0, p_pr)
        height = Length(space_after_emu + int(Pt(1)))
        yield RenderedInfo(spacer, height)
        layout_state.add_height(height)
