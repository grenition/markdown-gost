"""Блочная формула — ``$$...$$`` (T015).

Структура: невидимая таблица с тремя строками. Верхняя/нижняя строки дают
конфигурируемый вертикальный отступ, средняя строка — прежняя 1×2 раскладка:
левая ячейка с ``<m:oMath>`` (центрирован), правая — короткое «(N)» с
выравниванием по ``equation.numbering_alignment``. Это даёт «формула в
центре, номер у правого поля» — ГОСТ-практика.

Why OMML: формулы рендерятся как живая математика Word'а — редактируемые
в Word, корректный размер с ``<w:rPr><w:sz>`` на ``<m:r>``-ах. Известное
ограничение: LibreOffice (через unoserver конвертит DOCX→PDF) исторически
игнорирует size math-runs и рисует ~10pt вместо текста. В MS Word всё OK.

Нумерация — статическая: ``set_number(N)`` пишет «(N)» (или «N», если
``equation.parentheses=False``) в правую ячейку. SEQ-поля Word'а не
используем — единый стиль с Listing/Table/Image.

На одном экране формула — атомарный блок (если не помещается, целиком
уезжает на новую страницу).

Невалидный LaTeX → одиночный параграф-плейсхолдер «[Invalid equation: …]»
красным курсивом + warning в лог. Рендер не падает.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any, cast

from docx.document import Document as DocxDocument
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Length, Pt, RGBColor
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.config.units import parse_length, parse_pt
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.latex_math import (
    EquationError,
    apply_run_props,
    latex_to_omml,
)
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import (
    Renderable,
    RenderedInfo,
    RequiresNumbering,
    SubRenderable,
)

_log = logging.getLogger(__name__)

_PLACEHOLDER_COLOR = RGBColor(0xC0, 0x00, 0x00)

# Узкая правая ячейка с номером: достаточно ~36 точек для «(99)».
_NUMBER_CELL_PT = 36


class Equation(Renderable, RequiresNumbering):
    """Блочная формула с правой нумерацией ``(N)``."""

    numbering_category = "equation"

    def __init__(
        self,
        parent: DocxDocument,
        config: Config,
        node: ast.Equation,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._number: int | str | None = None

    def set_number(self, number: int | str) -> None:
        self._number = number

    @property
    def caption_text(self) -> str | None:
        """У формулы нет текстовой подписи — только номер."""

        return None

    # ------------------------------------------------------------------
    # размеры
    # ------------------------------------------------------------------

    def _content_dxa(self) -> int:
        section = self._parent.sections[0]
        page_w: Length = section.page_width or Length(0)
        left_m: Length = section.left_margin or Length(0)
        right_m: Length = section.right_margin or Length(0)
        content_emu = int(page_w) - int(left_m) - int(right_m)
        return int(round(content_emu / 914400 * 1440))

    def _number_cell_dxa(self) -> int:
        # 1pt = 20 dxa.
        return _NUMBER_CELL_PT * 20

    # ------------------------------------------------------------------
    # построение таблицы
    # ------------------------------------------------------------------

    def _build_table_shell(self, formula_dxa: int, number_dxa: int) -> Any:
        total_dxa = formula_dxa + number_dxa
        tbl = create_element("w:tbl")
        tbl_pr = create_element("w:tblPr")
        tbl_pr.append(
            create_element("w:tblW", {"w:w": str(total_dxa), "w:type": "dxa"})
        )
        tbl_pr.append(create_element("w:tblLayout", {"w:type": "fixed"}))
        # Невидимая обвязка — иначе формула обрастёт рамкой.
        borders_children = []
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            borders_children.append(
                create_element(
                    f"w:{side}",
                    {"w:val": "none", "w:sz": "0", "w:space": "0", "w:color": "auto"},
                )
            )
        tbl_pr.append(create_element("w:tblBorders", borders_children))
        tbl_pr.append(
            create_element(
                "w:tblCellMar",
                [
                    create_element("w:top", {"w:w": "0", "w:type": "dxa"}),
                    create_element("w:left", {"w:w": "0", "w:type": "dxa"}),
                    create_element("w:bottom", {"w:w": "0", "w:type": "dxa"}),
                    create_element("w:right", {"w:w": "0", "w:type": "dxa"}),
                ],
            )
        )
        tbl.append(tbl_pr)

        tbl_grid = create_element("w:tblGrid")
        tbl_grid.append(create_element("w:gridCol", {"w:w": str(formula_dxa)}))
        tbl_grid.append(create_element("w:gridCol", {"w:w": str(number_dxa)}))
        tbl.append(tbl_grid)
        return tbl

    def _build_left_cell(self, formula_dxa: int, omml: Any) -> Any:
        tc = create_element("w:tc")
        tc.append(
            create_element(
                "w:tcPr",
                [
                    create_element(
                        "w:tcW", {"w:w": str(formula_dxa), "w:type": "dxa"}
                    ),
                    create_element("w:vAlign", {"w:val": "center"}),
                ],
            )
        )
        p = create_element("w:p")
        p.append(
            create_element(
                "w:pPr",
                [
                    create_element("w:jc", {"w:val": "center"}),
                    create_element("w:ind", {"w:firstLine": "0"}),
                    create_element("w:spacing", {"w:before": "0", "w:after": "0"}),
                ],
            )
        )
        p.append(omml)
        tc.append(p)
        return tc

    def _build_right_cell(self, number_dxa: int) -> Any:
        spec = self._config.equation
        tc = create_element("w:tc")
        tc.append(
            create_element(
                "w:tcPr",
                [
                    create_element("w:tcW", {"w:w": str(number_dxa), "w:type": "dxa"}),
                    create_element("w:vAlign", {"w:val": "center"}),
                ],
            )
        )
        p = create_element("w:p")
        align_val = {
            "left": "left",
            "right": "right",
            "center": "center",
            "justify": "both",
        }[spec.numbering_alignment]
        p_pr = create_element(
            "w:pPr",
            [
                create_element("w:jc", {"w:val": align_val}),
                create_element("w:ind", {"w:firstLine": "0"}),
                create_element("w:spacing", {"w:before": "0", "w:after": "0"}),
            ],
        )
        p.append(p_pr)

        text = self._format_number_text(self._number or 0)
        run = create_element("w:r")
        run.append(create_element("w:t", text))
        p.append(run)
        tc.append(p)
        return tc

    def _build_spacer_row(self, total_dxa: int, height_twips: int) -> Any:
        tr = create_element("w:tr")
        tr.append(
            create_element(
                "w:trPr",
                [
                    create_element(
                        "w:trHeight",
                        {"w:val": str(height_twips), "w:hRule": "exact"},
                    ),
                ],
            )
        )
        tc = create_element("w:tc")
        tc.append(
            create_element(
                "w:tcPr",
                [
                    create_element("w:tcW", {"w:w": str(total_dxa), "w:type": "dxa"}),
                    create_element("w:gridSpan", {"w:val": "2"}),
                ],
            )
        )
        p = create_element("w:p")
        p.append(
            create_element(
                "w:pPr",
                [create_element("w:spacing", {"w:before": "0", "w:after": "0"})],
            )
        )
        tc.append(p)
        tr.append(tc)
        return tr

    def _format_number_text(self, number: int | str) -> str:
        if self._config.equation.parentheses:
            return f"({number})"
        return str(number)

    # ------------------------------------------------------------------
    # render
    # ------------------------------------------------------------------

    def _render_placeholder(
        self, latex: str, error: str, layout_state: LayoutState
    ) -> Generator[RenderedInfo | SubRenderable]:
        _log.warning(
            "invalid LaTeX equation %r: %s — rendering red placeholder",
            latex,
            error,
        )
        para = DocxParagraph(create_element("w:p"), self._parent)
        pf = para.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = 0
        pf.space_after = 0
        para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = para.add_run(f"[Invalid equation: {error}]")
        run.italic = True
        run.font.color.rgb = _PLACEHOLDER_COLOR
        font_pt = parse_pt(self._config.font.size)
        height = Length(int(Pt(font_pt * 1.5)))
        if height >= layout_state.remaining_page_height:
            height = Length(int(height) + int(layout_state.remaining_page_height))
        yield RenderedInfo(para, height)
        layout_state.add_height(height)

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        try:
            omml = latex_to_omml(self._node.latex)
        except EquationError as exc:
            yield from self._render_placeholder(
                self._node.latex, str(exc), layout_state
            )
            return

        font_pt = parse_pt(self._config.font.size)
        apply_run_props(
            omml, font_pt=font_pt, font_name=self._config.font.family
        )

        number_dxa = self._number_cell_dxa()
        formula_dxa = max(0, self._content_dxa() - number_dxa)
        tbl = self._build_table_shell(formula_dxa, number_dxa)
        total_dxa = formula_dxa + number_dxa
        space_before = parse_length(self._config.equation.space_before)
        space_after = parse_length(self._config.equation.space_after)

        space_before_twips = _length_to_twips(space_before)
        space_after_twips = _length_to_twips(space_after)
        if space_before_twips > 0:
            tbl.append(self._build_spacer_row(total_dxa, space_before_twips))
        tr = create_element("w:tr")
        tr.append(
            create_element(
                "w:trPr",
                [create_element("w:cantSplit")],
            )
        )
        tr.append(self._build_left_cell(formula_dxa, omml))
        tr.append(self._build_right_cell(number_dxa))
        tbl.append(tr)
        if space_after_twips > 0:
            tbl.append(self._build_spacer_row(total_dxa, space_after_twips))

        # Высота — 1.5×шрифт + поправка на структурную сложность (дроби,
        # суммы, корни). Грубо, но достаточно для page-break heuristics.
        depth = _math_depth(omml)
        height = Length(
            int(Pt(font_pt * 1.5 * (1 + 0.5 * depth)))
            + int(space_before)
            + int(space_after)
        )
        if int(height) >= int(layout_state.remaining_page_height):
            height = Length(int(height) + int(layout_state.remaining_page_height))

        yield RenderedInfo(
            DocxTable(tbl, cast(Any, self._parent)), height
        )
        layout_state.add_height(height)


def _length_to_twips(length: Length) -> int:
    """Convert python-docx EMU length to Word row-height twips."""

    return int(round(int(length) / 635))


def _math_depth(omml: Any) -> int:
    """Эвристика «вертикальная сложность»: считаем дроби / радикалы /
    n-ary операторы / скрипты / матрицы. Для page-break high-water-mark
    достаточно грубой оценки.
    """

    nsmap = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
    expressions = (
        ".//m:f",
        ".//m:rad",
        ".//m:nary",
        ".//m:sub",
        ".//m:sup",
        ".//m:sSub",
        ".//m:sSup",
        ".//m:sSubSup",
        ".//m:m",
    )
    return sum(len(omml.xpath(xp, namespaces=nsmap)) for xp in expressions)
