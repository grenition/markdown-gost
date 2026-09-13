"""Рендер картинки + подписи (T012).

Загрузка через :class:`Storage`. Нумерация — через :class:`Numberer`
(категория ``image``). Размер — авто, либо переопределение через
``ast.Length`` (``%`` / ``cm`` / ``mm`` / ``pt`` / ``px`` / ``in`` / ``auto``).

При битой ссылке выводим нейтральный визуальный плейсхолдер с warning, рендер
не падает.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from copy import copy
from io import BytesIO
from typing import Any

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Cm, Emu, Inches, Length, Mm, Pt, RGBColor
from docx.text.paragraph import Paragraph as DocxParagraph

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.image_placeholder import PLACEHOLDER_COPY, placeholder_png
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import (
    Renderable,
    RenderedInfo,
    RequiresNumbering,
    SubRenderable,
)
from markdown_gost.renderable.caption import Caption
from markdown_gost.storage.base import Storage, StorageError

_log = logging.getLogger(__name__)


class Image(Renderable, RequiresNumbering):
    """Картинка с подписью.

    Renderer вызывает ``set_number`` перед ``render`` (по интерфейсу
    :class:`RequiresNumbering`); в ``render`` мы оперируем уже выданным
    номером.
    """

    numbering_category = "image"

    def __init__(
        self,
        parent: Any,
        config: Config,
        node: ast.Image,
        storage: Storage,
    ) -> None:
        self._parent = parent
        self._config = config
        self._node = node
        self._storage = storage
        self._number: int | str | None = None
        self._invalid: bool = False

        self._docx_paragraph = DocxParagraph(create_element("w:p"), parent)
        self._docx_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        pf = self._docx_paragraph.paragraph_format
        pf.first_line_indent = 0
        pf.space_before = 0
        pf.space_after = 0
        pf.line_spacing = 1

        self._picture: Any | None = None
        self._load_picture()

    def set_number(self, number: int | str) -> None:
        self._number = number

    @property
    def docx_paragraph(self) -> DocxParagraph:
        return self._docx_paragraph

    @property
    def is_invalid(self) -> bool:
        return self._invalid

    @property
    def caption_text(self) -> str | None:
        """Текст подписи картинки (alt без префикса) — для RenderIndex."""

        return self._node.alt or None

    # ---- loading -----------------------------------------------------------

    def _load_picture(self) -> None:
        run = self._docx_paragraph.add_run()
        try:
            data = self._storage.fetch(self._node.src)
        except StorageError as exc:
            _log.warning("image %r unavailable: %s", self._node.src, exc)
            self._invalid = True
            self._render_placeholder(run)
            return
        try:
            self._picture = run.add_picture(BytesIO(data))
        except Exception as exc:  # python-docx wraps PIL errors generically
            _log.warning("image %r could not be embedded: %s", self._node.src, exc)
            self._invalid = True
            self._render_placeholder(run)

    def _render_placeholder(self, run: Any) -> None:
        """Embed a neutral icon card and its Russian label.

        Caption generation remains in :meth:`render`, so a failed image keeps
        its place in figure numbering and cross-references.
        """

        self._picture = run.add_picture(BytesIO(placeholder_png()))
        label = self._docx_paragraph.add_run()
        label.add_break()
        label.text = PLACEHOLDER_COPY
        label.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        label.font.size = Pt(10)

    # ---- sizing ------------------------------------------------------------

    def _resolve_dimensions(self, layout_state: LayoutState) -> tuple[Length, Length]:
        assert self._picture is not None
        original_width = Length(int(self._picture.width))
        original_height = Length(int(self._picture.height))
        column_width = layout_state.max_width
        page_height = layout_state.max_height

        aspect = (
            float(original_height) / float(original_width)
            if original_width
            else 1.0
        )

        explicit_w = self._convert_length(self._node.width, percent_base=column_width)
        explicit_h = self._convert_length(self._node.height, percent_base=page_height)

        if explicit_w is None and explicit_h is None:
            width = Length(min(int(original_width), int(column_width)))
            height = Length(int(width * aspect))
            return width, height

        if explicit_w is not None and explicit_h is None:
            width = explicit_w
            height = Length(int(width * aspect))
        elif explicit_h is not None and explicit_w is None:
            height = explicit_h
            inv_aspect = 1.0 / aspect if aspect else 1.0
            width = Length(int(height * inv_aspect))
        else:
            assert explicit_w is not None and explicit_h is not None
            width = explicit_w
            height = explicit_h

        if int(width) > int(column_width):
            _log.warning(
                "image %r width %d EMU > column %d EMU; clamping to column",
                self._node.src,
                int(width),
                int(column_width),
            )
            ratio = float(column_width) / float(width) if int(width) else 1.0
            width = column_width
            height = Length(int(int(height) * ratio))

        return width, height

    @staticmethod
    def _convert_length(
        spec: ast.Length | None, *, percent_base: Length
    ) -> Length | None:
        """Конвертировать AST-размер в EMU.

        ``percent_base`` — основа для процентов (ширина колонки для width,
        высота страницы для height). Возвращает None для ``None``/``auto``.
        """

        if spec is None or spec.unit == "auto":
            return None
        unit = spec.unit
        value = spec.value
        if unit == "%":
            return Length(int(float(percent_base) * value / 100.0))
        if unit == "cm":
            return Cm(value)
        if unit == "mm":
            return Mm(value)
        if unit == "pt":
            return Pt(value)
        if unit == "in":
            return Inches(value)
        if unit == "px":
            # 96 dpi (Web/CSS-конвенция).
            return Inches(value / 96.0)
        if unit == "emu":
            return Emu(int(value))
        # Неизвестная единица — игнорируем (ведём себя как «auto»).
        return None

    # ---- render ------------------------------------------------------------

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        width, height = self._resolve_dimensions(layout_state)
        assert self._picture is not None
        self._picture.width = width
        self._picture.height = height

        # Если картинка не помещается на текущей странице — двигаем на новую.
        # Renderer выше использует sentinel-механизм (height >= remaining
        # page height); компенсируем здесь явным «пустым» вертикальным
        # выравниванием — так же, как делал старый рендер.
        label_height = Pt(12) if self._invalid else Length(0)
        rendered_height: Length = Length(int(height) + int(label_height))
        if int(layout_state.remaining_page_height) < int(rendered_height):
            rendered_height = Length(
                int(rendered_height) + int(layout_state.remaining_page_height)
            )

        info = RenderedInfo(self._docx_paragraph, rendered_height)
        yield info
        layout_state.add_height(rendered_height)

        # Подпись (если задан caption-text через alt). Renderer всегда
        # добавляет номер, поэтому даже без alt мы рендерим «Рисунок N».
        caption = Caption(
            self._parent,
            self._config,
            category="image",
            number=self._number or 0,
            text=self._node.alt or None,
            before=False,
        )
        yield from caption.render(info, copy(layout_state))
