"""Контракт нативного preview для зарегистрированных шаблонов."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.preview_json import JsonValue, copy_json_layout, copy_json_style
from markdown_gost.render.render_index import RenderIndex


@dataclass
class PreviewTemplateContext:
    """Операции, доступные preview-обработчику шаблона.

    Контекст намеренно не зависит от внутренностей preview-builder: шаблон
    добавляет обычные preview-блоки и page break, а builder остаётся владельцем
    пагинации, модели и HTML-представления.
    """

    config: Config
    document_ast: ast.Document
    index: RenderIndex
    _add_block: Callable[..., None] = field(repr=False)
    _add_page_break: Callable[[], None] = field(repr=False)
    _current_page: Callable[[], int] = field(repr=False)
    _defer: Callable[[Callable[[], None]], None] = field(repr=False)
    template_name: str = ""

    @property
    def page(self) -> int:
        """Current 1-based preview page while the template is being emitted."""

        return self._current_page()

    def add_block(
        self,
        kind: str,
        text: str,
        *,
        style: dict[str, Any] | None = None,
        inlines: list[dict[str, Any]] | None = None,
        block_id: str | None = None,
        level: int | None = None,
        numbered: bool | None = None,
        number: str | None = None,
        anchor: str | None = None,
        layout: dict[str, Any] | None = None,
    ) -> dict[str, JsonValue] | None:
        """Emit a standard preview block using the builder's page layout."""

        if not isinstance(kind, str):
            raise ValueError("preview block kind must be a string")
        if not isinstance(text, str):
            raise ValueError("preview block text must be a string")
        if block_id is not None and not isinstance(block_id, str):
            raise ValueError("preview block id must be a string")
        if level is not None and (isinstance(level, bool) or not isinstance(level, int)):
            raise ValueError("preview block level must be an integer")
        if numbered is not None and not isinstance(numbered, bool):
            raise ValueError("preview block numbered flag must be a boolean")
        if number is not None and not isinstance(number, str):
            raise ValueError("preview block number must be a string")
        if anchor is not None and not isinstance(anchor, str):
            raise ValueError("preview block anchor must be a string")
        safe_style = copy_json_style(style)
        safe_layout = copy_json_layout(layout)
        self._add_block(
            kind,
            text,
            style=safe_style,
            inlines=inlines,
            block_id=block_id,
            level=level,
            numbered=numbered,
            number=number,
            anchor=anchor,
            layout=safe_layout,
        )
        return safe_layout

    def add_page_break(self) -> None:
        """Force following preview content onto a fresh page."""

        self._add_page_break()

    def defer(self, callback: Callable[[], None]) -> None:
        """Run ``callback`` after headings and their pages are known."""

        self._defer(callback)
