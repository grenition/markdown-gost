"""Рендер markdown-таблиц с подписью «Таблица N — …» (T013).

Текущая реализация — **native mode**: один сплошной ``<w:tbl>``, перенос
через стыки страниц делает Word/LibreOffice. Используется, когда
``config.captions.continuation_break`` выключен (default).

Управление layout-ом:
- если все ``column_widths`` отсутствуют или ``auto`` — пишем
  ``<w:tblLayout w:type="autofit"/>`` без явных ``<w:gridCol>``-ширин:
  Word сам подберёт колонки по содержимому;
- если хотя бы одна колонка задана не-``auto`` — переключаем на
  ``<w:tblLayout w:type="fixed"/>``, явные значения транслируются в
  ``<w:gridCol>`` + ``<w:tcW w:type="dxa"/>``; колонки с ``auto`` получают
  остаток равномерно (``(total − sum_explicit) / count_auto``).
- ``row_heights`` — если ``auto``, ``<w:trHeight>`` не выставляем; если задано
  явно, пишем ``<w:trHeight w:val="…" w:hRule="atLeast"/>`` (минимум, чтобы
  длинный текст не обрезался).
- ``config.table.repeat_header_on_break: true`` транслируется в
  ``<w:tblHeader/>`` на строках шапки — Word повторит шапку на новой странице.
- ``<w:cantSplit/>`` ставится в ``<w:trPr>`` каждой строки, чтобы строка не
  рвалась внутри между страниц.
- параграфы ячеек шапки несут ``w:keepNext`` — шапка не остаётся одна
  внизу страницы без первой строки тела (в связке с keepNext подписи
  блок «подпись + шапка + первая строка» переносится целиком).

Manual page-break (наша подпись «Продолжение таблицы») вынесен отдельной
задачей T013 (продолжение): требует попаточечного измерения каждой строки
ParagraphSizer-ом и разреза в нескольких ``<w:tbl>``.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from copy import copy, deepcopy
from dataclasses import dataclass
from typing import Any, cast

from docx.document import Document as DocxDocument
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Length, Pt
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length, parse_pt
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex
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
from markdown_gost.renderable.paragraph import Paragraph as ParagraphRenderable
from markdown_gost.storage.base import Storage

_log = logging.getLogger(__name__)

# Параметры рамок таблицы. Для T013 хватит сплошной 0.5pt линии — стандарт ГОСТ.
# Если потребуется конфигурация, подключим через ``config.table.border_style``.
_BORDER_SIZE_EIGHTHS = "4"  # 4/8 pt = 0.5pt
_BORDER_COLOR = "000000"

_ALIGN_MAP: dict[str, WD_PARAGRAPH_ALIGNMENT] = {
    "left": WD_PARAGRAPH_ALIGNMENT.LEFT,
    "right": WD_PARAGRAPH_ALIGNMENT.RIGHT,
    "center": WD_PARAGRAPH_ALIGNMENT.CENTER,
}

# Внутренние отступы ячейки (tblCellMar) — используются и при построении xml,
# и при измерении высоты строки. dxa.
_CELL_PAD_TOP_DXA = 55
_CELL_PAD_LEFT_DXA = 108
_CELL_PAD_BOTTOM_DXA = 55
_CELL_PAD_RIGHT_DXA = 108


@dataclass
class _PreRow:
    """Кэшированная w:tr вместе с измеренной высотой и флагом шапки.

    Используется в обоих режимах: native кладёт все pre-rows в один
    ``<w:tbl>``, manual-режим — нарезает по chunk'ам и копирует через
    ``deepcopy`` (xml-элемент нельзя присоединить в два дерева сразу).
    """

    xml: Any
    height: Length
    is_header: bool


def _emu_to_dxa(emu: Length) -> int:
    """EMU → 20ths of a point (dxa). 1 dxa = 1/1440 inch; 1 emu = 1/914400 inch."""

    return int(round(int(emu) / 914400 * 1440))


def _length_to_dxa(spec: ast.Length, *, percent_base_emu: Length) -> int | None:
    """Перевести AST-размер в dxa. ``auto`` → ``None``."""

    if spec.unit == "auto":
        return None
    if spec.unit == "%":
        return _emu_to_dxa(Length(int(int(percent_base_emu) * spec.value / 100.0)))
    # parse_length поддерживает cm/mm/pt/in/px из строки; собираем строку из value+unit.
    return _emu_to_dxa(parse_length(f"{spec.value}{spec.unit}"))


class Table(Renderable, RequiresNumbering):
    """Markdown-таблица с подписью.

    Парсер передаёт сюда уже разобранные ``column_widths`` / ``row_heights``
    (списки той же длины, что и число столбцов/строк) — фабрика
    выбрасывает ``ValueError`` ещё на стадии construct, если число значений
    не совпадает.
    """

    numbering_category = "table"

    def __init__(
        self,
        parent: DocxDocument,
        config: Config,
        node: ast.Table,
        *,
        caption_text: str | None = None,
        column_widths: list[ast.Length] | None = None,
        row_heights: list[ast.Length] | None = None,
        storage: Storage | None = None,
        bibliography: BibliographyIndex | None = None,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._caption_text = caption_text
        self._number: int | str | None = None
        self._storage = storage
        self._bibliography = bibliography

        self._ncols = max((len(row.cells) for row in node.rows), default=0)
        self._nrows = len(node.rows)

        if column_widths is not None and len(column_widths) != self._ncols:
            raise ValueError(
                f"widths: expected {self._ncols} values, got {len(column_widths)}"
            )
        if row_heights is not None and len(row_heights) != self._nrows:
            raise ValueError(
                f"heights: expected {self._nrows} values, got {len(row_heights)}"
            )

        self._column_widths = column_widths
        self._row_heights = row_heights
        self._is_fixed_layout = self._column_widths is not None and any(
            w.unit != "auto" for w in self._column_widths
        )
        # Manual page-break (наш собственный разрез + подпись «Продолжение
        # таблицы») включается тогглером ``captions.continuation_break``.
        # Иначе рендерим один <w:tbl> и отдаём перенос Word/LO.
        self._manual_breaks = self._config.captions.continuation_break

        # Кешируем шаблоны tblPr/tblGrid и список <w:tr>+высоты — в обоих
        # режимах. Native собирает один tbl сейчас же; manual — разрезает
        # на чанки в render().
        self._tbl_pr_template = self._build_tbl_pr()
        self._tbl_grid_template = self._build_tbl_grid()
        self._rows: list[_PreRow] = self._build_pre_rows()
        self._docx_table: DocxTable | None = (
            None if self._manual_breaks else self._assemble_table(self._rows)
        )

    def set_number(self, number: int | str) -> None:
        self._number = number

    @property
    def docx_table(self) -> DocxTable | None:
        return self._docx_table

    @property
    def caption_text(self) -> str | None:
        """Текст подписи таблицы (без префикса «Таблица N — »)."""

        return self._caption_text

    def _font_pt(self) -> float:
        """Эффективный размер шрифта таблицы в pt.

        Если ``config.table.font_size`` задан — используется он, иначе
        наследуется от глобального ``config.font.size``. Возвращаемое
        значение участвует и в измерениях (autofit, row height), и в
        применении ``run.font.size`` на ячейки.
        """

        override = self._config.table.font_size
        if override is not None:
            return parse_pt(override)
        return parse_pt(self._config.font.size)

    # ---- table construction ------------------------------------------------

    def _build_pre_rows(self) -> list[_PreRow]:
        """Однократно строим w:tr + измеряем высоту по реальному содержимому."""

        return [self._build_pre_row(idx, row) for idx, row in enumerate(self._node.rows)]

    def _assemble_table(self, rows: list[_PreRow]) -> DocxTable:
        """Собрать <w:tbl> из готовых _PreRow.

        Для каждого вызова деepcopy-им шаблоны tblPr/tblGrid и xml каждой
        строки — иначе lxml-элемент окажется в нескольких деревьях.
        """

        tbl = create_element("w:tbl")
        tbl.append(deepcopy(self._tbl_pr_template))
        tbl.append(deepcopy(self._tbl_grid_template))
        for r in rows:
            tbl.append(deepcopy(r.xml))
        return DocxTable(tbl, cast(Any, self._parent))

    def _build_tbl_pr(self) -> Any:
        tbl_pr = create_element("w:tblPr")
        # ширина таблицы целиком: total из gridCol-ширин (явных или
        # content-based estimate). LO нестабильно отрабатывает type="auto",
        # поэтому всегда пишем dxa-сумму — рендер получится одинаковым.
        total_dxa = sum(self._column_dxas())
        tbl_pr.append(
            create_element(
                "w:tblW",
                {"w:w": str(total_dxa), "w:type": "dxa"},
            )
        )
        layout_type = "fixed" if self._is_fixed_layout else "autofit"
        tbl_pr.append(create_element("w:tblLayout", {"w:type": layout_type}))

        # Сетка границ: одинарная линия для всех направлений + insideH/insideV.
        tbl_pr.append(self._build_tbl_borders())
        # Промежуток внутри ячеек.
        tbl_pr.append(
            create_element(
                "w:tblCellMar",
                [
                    create_element("w:top", {"w:w": "55", "w:type": "dxa"}),
                    create_element("w:left", {"w:w": "108", "w:type": "dxa"}),
                    create_element("w:bottom", {"w:w": "55", "w:type": "dxa"}),
                    create_element("w:right", {"w:w": "108", "w:type": "dxa"}),
                ],
            )
        )
        return tbl_pr

    def _build_tbl_borders(self) -> Any:
        children = []
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            children.append(
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
        return create_element("w:tblBorders", children)

    def _column_dxas(self) -> list[int]:
        """Единая точка получения dxa-ширин столбцов.

        - fixed layout (есть хотя бы один не-``auto`` ``widths[i]``) →
          ``_resolve_column_dxas`` (явные + остаток на ``auto``).
        - autofit (атрибутов нет или все ``auto``) → content-based estimate,
          пропорционально масштабированный под полосу страницы. Так LO/Word
          получают неравные колонки по содержимому, не схлопываясь в равные.
        """

        if self._is_fixed_layout:
            return self._resolve_column_dxas()
        return self._estimate_autofit_dxas()

    def _estimate_autofit_dxas(self) -> list[int]:
        """Оценить ширины столбцов в dxa по самому длинному тексту в колонке.

        Алгоритм:
        1. natural[i] = max(длина plain-текста ячейки) × char_dxa + padding.
        2. Пропорционально масштабируем сумму к ``content_width`` (полоса страницы).
        Если все ячейки пустые — равномерное распределение.
        """

        if self._ncols == 0:
            return []
        font_pt = self._font_pt()
        # ~half-em на символ: для пропорциональных шрифтов это грубый, но
        # достаточный для оценки автофита; реальное измерение делает рендер.
        char_dxa = max(int(font_pt * 11), 100)
        cell_padding = 216  # left + right из tblCellMar
        min_col = char_dxa * 2 + cell_padding  # минимум на 2 символа

        natural: list[int] = [min_col] * self._ncols
        for row in self._node.rows:
            for col_idx, cell in enumerate(row.cells[: self._ncols]):
                text_len = len(_plain_text_of_cell(cell))
                width = text_len * char_dxa + cell_padding
                if width > natural[col_idx]:
                    natural[col_idx] = width

        section = self._parent.sections[0]
        page_w: Length = section.page_width or Length(0)
        left_m: Length = section.left_margin or Length(0)
        right_m: Length = section.right_margin or Length(0)
        content_dxa = _emu_to_dxa(
            Length(int(page_w) - int(left_m) - int(right_m))
        )

        total = sum(natural)
        if total <= 0:
            per = content_dxa // self._ncols
            return [per] * self._ncols
        # Масштабируем пропорционально к content_dxa (полоса заполнена).
        scale = content_dxa / total
        widths = [max(int(round(n * scale)), min_col) for n in natural]
        # Нормализуем сумму ровно к content_dxa, поглощая остаток в самой широкой.
        diff = content_dxa - sum(widths)
        if diff != 0:
            widest_idx = max(range(self._ncols), key=lambda i: widths[i])
            widths[widest_idx] += diff
        return widths

    def _resolve_column_dxas(self) -> list[int]:
        """Вернуть список целых dxa-значений для всех столбцов в fixed-layout.

        В autofit-режиме не вызывается. В fixed-режиме ``auto`` колонки делят
        остаток поровну — отрицательный остаток поднимает ``ValueError``.
        """

        assert self._column_widths is not None
        section = self._parent.sections[0]
        page_w: Length = section.page_width or Length(0)
        left_m: Length = section.left_margin or Length(0)
        right_m: Length = section.right_margin or Length(0)
        content_emu = Length(int(page_w) - int(left_m) - int(right_m))
        content_dxa = _emu_to_dxa(content_emu)

        explicit: list[int | None] = []
        explicit_total = 0
        auto_count = 0
        for spec in self._column_widths:
            dxa = _length_to_dxa(spec, percent_base_emu=content_emu)
            explicit.append(dxa)
            if dxa is None:
                auto_count += 1
            else:
                explicit_total += dxa
        if auto_count == 0:
            return [int(d) for d in explicit if d is not None]
        remainder = content_dxa - explicit_total
        if remainder <= 0:
            raise ValueError(
                f"widths: explicit columns sum to {explicit_total} dxa "
                f"but content area is only {content_dxa} dxa — reduce explicit values"
            )
        per_auto = remainder // auto_count
        out: list[int] = []
        for dxa in explicit:
            out.append(dxa if dxa is not None else per_auto)
        return out

    def _build_tbl_grid(self) -> Any:
        children = []
        for dxa in self._column_dxas():
            children.append(create_element("w:gridCol", {"w:w": str(dxa)}))
        return create_element("w:tblGrid", children)

    def _build_pre_row(self, row_idx: int, row: ast.TableRow) -> _PreRow:
        """Построить <w:tr> и измерить высоту строки по реальному тексту.

        Высота строки = max(высота параграфа в каждой ячейке) + верхний и
        нижний паддинг tblCellMar. Если в конфиге задана явная row_heights[i]
        — берём максимум измеренного и явного (atLeast).
        """

        tr_pr_children: list[Any] = []
        tr_pr_children.append(create_element("w:cantSplit"))
        # tblHeader на шапке — только в native режиме. В manual мы сами
        # дублируем header rows, поэтому Word'у этот маркер не нужен (и даже
        # вреден: он попытается продублировать шапку поверх нашей).
        if (
            row.header
            and not self._manual_breaks
            and self._config.table.repeat_header_on_break
        ):
            tr_pr_children.append(create_element("w:tblHeader"))
        if self._row_heights is not None:
            spec = self._row_heights[row_idx]
            if spec.unit != "auto":
                dxa = _length_to_dxa(spec, percent_base_emu=Length(0))
                if dxa is not None and dxa > 0:
                    tr_pr_children.append(
                        create_element(
                            "w:trHeight",
                            {"w:val": str(dxa), "w:hRule": "atLeast"},
                        )
                    )
        tr = create_element("w:tr")
        if tr_pr_children:
            tr.append(create_element("w:trPr", tr_pr_children))

        column_dxas = self._column_dxas()
        cell_paragraphs: list[DocxParagraph] = []
        for col_idx in range(self._ncols):
            cell = row.cells[col_idx] if col_idx < len(row.cells) else None
            tc, cell_p = self._build_tc(
                cell,
                col_dxa=column_dxas[col_idx] if column_dxas else None,
                is_header=row.header,
            )
            tr.append(tc)
            cell_paragraphs.append(cell_p)

        height = self._measure_row_height(
            row_idx, row, column_dxas, cell_paragraphs
        )
        return _PreRow(xml=tr, height=height, is_header=row.header)

    def _build_tc(
        self,
        cell: ast.TableCell | None,
        *,
        col_dxa: int | None,
        is_header: bool,
    ) -> tuple[Any, DocxParagraph]:
        tc = create_element("w:tc")
        tc_pr_children: list[Any] = []
        if col_dxa is not None:
            tc_pr_children.append(
                create_element("w:tcW", {"w:w": str(col_dxa), "w:type": "dxa"})
            )
        else:
            tc_pr_children.append(
                create_element("w:tcW", {"w:w": "0", "w:type": "auto"})
            )
        tc.append(create_element("w:tcPr", tc_pr_children))

        # Содержимое ячейки — один параграф с inline-нодами. Используем
        # Paragraph renderable, чтобы получить полную поддержку ссылок/кода/
        # форматирования; затем подменяем хост — переносим w:p в нашу w:tc.
        # storage пробрасывается, иначе inline-картинки в ячейке упадут в
        # текстовый fallback `[src]` (paragraph.py:_add_inline_image).
        para_renderable = ParagraphRenderable(
            self._parent,
            self._config,
            storage=self._storage,
            bibliography=self._bibliography,
        )
        if cell is not None:
            para_renderable.add_inline_nodes(cell.children)
        else:
            # Пустая ячейка — добавляем пустой параграф (он обязателен в w:tc).
            para_renderable.add_inline_nodes([])

        cell_p = para_renderable.docx_paragraph
        # В ячейках убираем первую отступную строку и центрируем по выравниванию,
        # заданному в md (`:--` / `:-:` / `--:`). Шапка — жирная по умолчанию.
        cell_p.paragraph_format.first_line_indent = 0
        cell_p.paragraph_format.space_before = 0
        cell_p.paragraph_format.space_after = 0
        if cell is not None and cell.align is not None:
            cell_p.alignment = _ALIGN_MAP[cell.align]
        if is_header and self._config.table.header_bold:
            for run in cell_p.runs:
                run.bold = True
        # Шапка не отрывается от первого body-row: keepNext на параграфах
        # ячеек шапки не даёт шапке остаться одной внизу страницы.
        if is_header:
            cell_p.paragraph_format.keep_with_next = True
        if self._config.table.font_size is not None:
            cell_font_size = Pt(parse_pt(self._config.table.font_size))
            for run in cell_p.runs:
                run.font.size = cell_font_size

        tc.append(cell_p._p)
        return tc, cell_p

    def _measure_row_height(
        self,
        row_idx: int,
        row: ast.TableRow,
        column_dxas: list[int],
        cell_paragraphs: list[DocxParagraph],
    ) -> Length:
        """Вернуть высоту строки в EMU (для page-break-логики).

        Алгоритм:
        - для каждой ячейки считаем ParagraphSizer'ом высоту её параграфа,
          ширина = column_dxa в EMU за вычетом L+R cell-padding;
        - берём максимум по ячейкам, прибавляем top+bottom cell-padding;
        - прибавляем константный border safety (~1.5pt) — компенсация толщины
          бордеров (≈0.5pt × 2) и субпойнтового округления LO; запас именно
          аддитивный, не пропорциональный, потому что физический пробел не
          зависит от размера шрифта (мультипликатор 1.10x на мелких шрифтах
          съедал по 1-2 строки на странице);
        - если задано явное ``row_heights[i]`` — клампим к нему снизу
          (atLeast: минимум, реальная высота не меньше задана).
        """

        max_cell_height = 0
        for col_idx, cell_p in enumerate(cell_paragraphs):
            col_dxa = column_dxas[col_idx] if col_idx < len(column_dxas) else 0
            inner_dxa = max(0, col_dxa - _CELL_PAD_LEFT_DXA - _CELL_PAD_RIGHT_DXA)
            inner_emu = int(inner_dxa * 914400 / 1440)
            try:
                result = ParagraphSizer(
                    cell_p, None, Length(inner_emu)
                ).calculate_height()
            except (ValueError, RuntimeError) as exc:  # pragma: no cover — defensive
                _log.debug("ParagraphSizer failed for cell, fallback: %s", exc)
                # Fallback: одна строка с базовым line_height.
                font_pt = self._font_pt()
                fallback = int(Pt(font_pt * self._config.font.line_spacing))
                if fallback > max_cell_height:
                    max_cell_height = fallback
                continue
            # ``full`` = before + line_height * line_spacing * lines + after.
            # LO применяет полный leading к каждой строке (включая первую),
            # поэтому для высоты ячейки берём именно ``full`` — не ``base``,
            # которое занижает оценку на 0.5x line_height и приводит к тому,
            # что LO сам режет наш чанк между страницами.
            cell_h = int(result.full)
            if cell_h > max_cell_height:
                max_cell_height = cell_h

        cell_pad_emu = int((_CELL_PAD_TOP_DXA + _CELL_PAD_BOTTOM_DXA) * 914400 / 1440)
        # T013a: аддитивный запас на бордеры таблицы (~0.5pt × 2 = 1pt) +
        # субpt-округление LO. Старый мультипликатор 1.10x давал
        # пропорциональную ошибку — на мелких шрифтах терялось до 2 строк
        # на страницу. Реальный пробел физически константен.
        border_safety = Pt(1.5)
        height = int(max_cell_height + cell_pad_emu + border_safety)

        # ``row_heights[i]`` — нижняя граница (atLeast).
        if self._row_heights is not None:
            spec = self._row_heights[row_idx]
            if spec.unit != "auto":
                explicit = int(parse_length(f"{spec.value}{spec.unit}"))
                if explicit > height:
                    height = explicit
        # Помимо row_heights, для шапок имеет смысл иметь минимум — иначе
        # пустая шапка получится плоской. Минимум = 1 строка + padding.
        font_pt = self._font_pt()
        min_row = int(Pt(font_pt * self._config.font.line_spacing)) + cell_pad_emu
        if height < min_row:
            height = min_row
        return Length(height)

    # ---- height estimation -------------------------------------------------

    def _estimate_height(self, max_width: Length) -> Length:
        """Грубая оценка высоты таблицы для layout-трекера.

        Word/LibreOffice сами решат, как ужать или растянуть колонки в native-
        режиме, поэтому достаточно консервативной оценки. Пренебрегаем
        переносом строк: каждая строка считается одно-строчной плюс паддинг.
        Если задана явная ``row_heights[i]`` — берём её. Иначе используем
        font.line_height * line_spacing + 110dxa (≈ внутренние отступы).
        """

        font_size_pt = self._font_pt()
        line_spacing = self._config.font.line_spacing
        default_row_emu = Pt(font_size_pt * line_spacing) + Pt(4)

        total = 0
        for row_idx in range(self._nrows):
            if self._row_heights is not None:
                spec = self._row_heights[row_idx]
                if spec.unit != "auto":
                    explicit = parse_length(f"{spec.value}{spec.unit}")
                    total += int(explicit)
                    continue
            total += int(default_row_emu)
        return Length(total)

    # ---- render ------------------------------------------------------------

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        # Подпись идёт ПЕРЕД таблицей: если в конце страницы не помещается,
        # Caption сам выставит page_break_before и сдвинется на новую страницу.
        caption = Caption(
            self._parent,
            self._config,
            category="table",
            number=self._number or 0,
            text=self._caption_text,
            before=True,
        )
        # T013b: ``table.space_before`` накладывается ПОВЕРХ значения, которое
        # Caption уже выставил из ``captions.table.space_before``. Мотивация:
        # для блок-элементов с подписью «перед» у пользователя обычно одна
        # ментальная модель — отступ блока, а не подписи отдельно. Конфликт
        # с captions.table.space_before решается «table выигрывает».
        table_space_before_emu = int(parse_length(self._config.table.space_before))
        if table_space_before_emu > 0:
            caption.docx_paragraph.paragraph_format.space_before = Length(
                table_space_before_emu
            )

        last_caption_info: RenderedInfo | None = None
        for item in caption.render(previous_rendered, copy(layout_state)):
            if isinstance(item, RenderedInfo):
                last_caption_info = item
            yield item
        if last_caption_info is not None:
            layout_state.add_height(last_caption_info.height)

        if self._manual_breaks:
            yield from self._render_manual(layout_state)
        else:
            assert self._docx_table is not None  # native mode: построен в __init__
            table_height = sum((int(r.height) for r in self._rows), 0)
            yield RenderedInfo(self._docx_table, Length(table_height))
            layout_state.add_height(Length(table_height))
            # T013b: trailing spacer-параграф (если задан space_after).
            yield from self._emit_trailing_spacer(layout_state)

    # ---- manual page-break (continuation_label) ----------------------------

    def _render_manual(
        self, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        """Разрезать таблицу на чанки и вставлять «Продолжение таблицы N»."""

        header_rows = [r for r in self._rows if r.is_header]
        body_rows = [r for r in self._rows if not r.is_header]
        header_height = sum((int(r.height) for r in header_rows), 0)

        # Текущий накапливаемый chunk: всегда стартует с шапки.
        chunk: list[_PreRow] = list(header_rows)
        chunk_height: int = header_height
        is_first_chunk = True

        def flush_chunk() -> Generator[RenderedInfo | SubRenderable]:
            nonlocal chunk, chunk_height, is_first_chunk
            if not chunk or chunk == header_rows:
                # Только шапка без тела — не выводим (вышло, что предыдущий
                # body_row сам перешёл на новую страницу).
                return
            tbl = self._assemble_table(chunk)
            yield RenderedInfo(tbl, Length(chunk_height))
            layout_state.add_height(Length(chunk_height))
            is_first_chunk = False
            chunk = list(header_rows)
            chunk_height = header_height

        for body_row in body_rows:
            row_h = int(body_row.height)
            remaining = int(layout_state.remaining_page_height)
            # Если строка не помещается на текущую страницу и в чанке уже
            # есть тело — флешим чанк и стартуем новую страницу.
            if chunk_height + row_h > remaining and len(chunk) > len(header_rows):
                yield from flush_chunk()
                # Continuation paragraph с page_break_before — съедает остаток
                # страницы, выводит подпись «Продолжение таблицы N».
                cont_para, cont_h = self._build_continuation(layout_state)
                yield RenderedInfo(cont_para, cont_h)
                layout_state.add_height(cont_h)
            chunk.append(body_row)
            chunk_height += row_h

        # Последний чанк (если в нём есть тело).
        if len(chunk) > len(header_rows):
            yield from flush_chunk()
        elif is_first_chunk and chunk:
            # Совсем пустая таблица (только шапка) — всё равно выведем.
            tbl = self._assemble_table(chunk)
            yield RenderedInfo(tbl, Length(chunk_height))
            layout_state.add_height(Length(chunk_height))
        # T013b: trailing spacer ТОЛЬКО после последнего chunk'а (не на каждом).
        # На промежуточных «Продолжение таблицы» spacer не нужен — иначе на
        # стыке страниц получим лишний пустой пробел.
        yield from self._emit_trailing_spacer(layout_state)

    def _emit_trailing_spacer(
        self, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        """Сгенерировать пустой параграф-разделитель после таблицы.

        Высота параграфа = ``space_after + 1pt`` (1pt — line height строки
        spacer'а через ``w:line="20" w:lineRule="exact"``). Пустой параграф
        фактически выглядит как чистый отступ перед следующим блоком.

        Если ``table.space_after == 0pt`` — spacer не эмитится (zero-cost
        для существующих кейсов с дефолтом).
        """

        space_after_emu = int(parse_length(self._config.table.space_after))
        if space_after_emu <= 0:
            return
        # dxa = 1/20 pt; Pt(1) = 12700 EMU; 1 EMU * 1440 / 914400 = dxa.
        space_dxa = int(round(space_after_emu / 914400 * 1440))
        spacer_p = DocxParagraph(create_element("w:p"), self._parent)
        p_pr = create_element(
            "w:pPr",
            [
                create_element(
                    "w:spacing",
                    {
                        "w:before": str(space_dxa),
                        "w:after": "0",
                        # 1pt line height фиксированной величины — параграф
                        # минимально занимает место, видимый отступ — w:before.
                        "w:line": "20",
                        "w:lineRule": "exact",
                    },
                ),
                # Не наследуем first_line_indent от Normal — для пустого
                # параграфа это не имеет смысла.
                create_element("w:ind", {"w:firstLine": "0"}),
            ],
        )
        spacer_p._p.insert(0, p_pr)
        height = Length(space_after_emu + int(Pt(1)))
        yield RenderedInfo(spacer_p, height)
        layout_state.add_height(height)

    def _build_continuation(
        self, layout_state: LayoutState
    ) -> tuple[DocxParagraph, Length]:
        """Параграф «Продолжение таблицы N» с page_break_before.

        Высота возвращается как ``remaining_page_height + измеренная``,
        чтобы трекер layout правильно перешагнул на новую страницу.
        ``space_before`` берётся из ``captions.table.space_before`` — Word
        применяет его и поверх page-break, поэтому подпись продолжения
        получает такой же воздух сверху, как обычная подпись таблицы.
        """

        spec = self._config.captions.table
        text = f"Продолжение таблицы {self._number or 0}"
        para_renderable = ParagraphRenderable(
            self._parent,
            self._config,
            storage=self._storage,
            bibliography=self._bibliography,
        )
        para_renderable.add_inline_nodes([ast.Text(text=text)])
        cell_p = para_renderable.docx_paragraph
        pf = cell_p.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = Length(int(parse_length(spec.space_before)))
        pf.space_after = 0
        if spec.line_spacing is not None:
            pf.line_spacing = spec.line_spacing
        pf.page_break_before = True
        # Подпись продолжения не отрывается от первой строки чанка (w:keepNext).
        pf.keep_with_next = True

        # Применим стиль подписи таблицы (italic/bold/alignment).
        if spec.italic:
            for run in cell_p.runs:
                run.italic = True
        if spec.bold:
            for run in cell_p.runs:
                run.bold = True
        cell_p.alignment = _ALIGN_MAP.get(spec.alignment, WD_PARAGRAPH_ALIGNMENT.LEFT)

        sizer_height = ParagraphSizer(
            cell_p, None, layout_state.max_width
        ).calculate_height()
        full_height = int(sizer_height.full) + int(layout_state.remaining_page_height)
        return cell_p, Length(full_height)


def _plain_text_of_cell(cell: ast.TableCell) -> str:
    """Конкатенация всего видимого текста ячейки для оценки natural-width.

    Inline-форматтеры (Strong/Emphasis/Underline/Link) — рекурсивно. InlineCode
    — учитываем как обычный текст той же длины. Reference считаем по длине
    name (приближённая оценка, в реальности это будет цифра).
    """

    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ast.Text):
            parts.append(node.text)
        elif isinstance(node, ast.InlineCode):
            parts.append(node.code)
        elif isinstance(node, ast.Reference):
            parts.append(node.name or "0")
        elif isinstance(node, ast.LineBreak):
            parts.append(" ")
        elif hasattr(node, "children"):
            for child in node.children:
                walk(child)

    for child in cell.children:
        walk(child)
    return "".join(parts)
