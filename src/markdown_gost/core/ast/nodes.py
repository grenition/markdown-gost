"""Расширенный AST для markdown_gost.

Узлы стабильны: каждый имеет ``node_id`` и опциональную ``source_position``
для будущей подсветки ошибок и трассировки. Дерево формирует
:func:`markdown_gost.core.parser.parse`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourcePosition:
    start_line: int | None = None
    end_line: int | None = None
    raw_text: str | None = None


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass(eq=False)
class Node:
    node_id: str = field(default_factory=_new_id)
    source_position: SourcePosition | None = None
    identifier: str | None = None


@dataclass(eq=False)
class InlineNode(Node):
    pass


@dataclass(eq=False)
class BlockNode(Node):
    pass


# ---- inline ----------------------------------------------------------------


@dataclass(eq=False)
class Text(InlineNode):
    text: str = ""


@dataclass(eq=False)
class Emphasis(InlineNode):
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class Strong(InlineNode):
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class Strikethrough(InlineNode):
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class Underline(InlineNode):
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class Link(InlineNode):
    url: str = ""
    title: str | None = None
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class InlineCode(InlineNode):
    code: str = ""


@dataclass(eq=False)
class LineBreak(InlineNode):
    soft: bool = False


@dataclass(eq=False)
class InlineEquation(InlineNode):
    latex: str = ""


@dataclass(eq=False)
class Reference(InlineNode):
    """Automatic cross-reference ``[](#id)``; resolved before rendering."""

    type: str = ""
    name: str = ""


@dataclass(eq=False)
class Citation(InlineNode):
    """Библиографическая ссылка ``[@key]``."""

    key: str = ""


# ---- block -----------------------------------------------------------------


@dataclass(eq=False)
class Paragraph(BlockNode):
    children: list[InlineNode] = field(default_factory=list)


@dataclass(eq=False)
class Heading(BlockNode):
    level: int = 1
    numbered: bool = True
    children: list[InlineNode] = field(default_factory=list)
    appendix: bool = False


@dataclass(eq=False)
class AppendixStart(BlockNode):
    title: str | None = None


@dataclass(eq=False)
class AppendixEnd(BlockNode):
    pass


@dataclass
class Length:
    """Размер картинки. ``unit='auto'`` означает автомасштаб."""

    value: float = 0.0
    unit: str = "auto"


@dataclass(eq=False)
class Image(InlineNode):
    src: str = ""
    alt: str = ""
    title: str | None = None
    width: Length | None = None
    height: Length | None = None


@dataclass(eq=False)
class Caption(BlockNode):
    """Trailing caption, normalized before its object in the AST.

    ``attrs`` хранит сырые ключ→значение из блока ``{key="value" ...}`` после
    текста (например, ``widths`` / ``heights`` для таблиц). Парсинг конкретных
    значений делает фабрика renderable'ов — у неё есть нужный контекст.
    """

    target: str = ""
    text: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass(eq=False)
class TableCell(Node):
    children: list[InlineNode] = field(default_factory=list)
    align: str | None = None  # left | center | right
    header: bool = False


@dataclass(eq=False)
class TableRow(Node):
    cells: list[TableCell] = field(default_factory=list)
    header: bool = False


@dataclass(eq=False)
class Table(BlockNode):
    rows: list[TableRow] = field(default_factory=list)
    # Явные ширины столбцов / высоты строк, заданные через ``{widths="..." heights="..."}``
    # из атрибутов объекта. ``None`` означает «не задано» — autofit по содержимому.
    # Если задан хотя бы один список, его длина строго равна числу столбцов/строк.
    column_widths: list[Length] | None = None
    row_heights: list[Length] | None = None


@dataclass(eq=False)
class Listing(BlockNode):
    language: str | None = None
    code: str = ""


@dataclass(eq=False)
class BibliographySource(Node):
    id: str = ""
    type: str = "other"
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False)
class Bibliography(BlockNode):
    sources: list[BibliographySource] = field(default_factory=list)


@dataclass(eq=False)
class Equation(BlockNode):
    latex: str = ""


@dataclass(eq=False)
class ListItem(Node):
    children: list[Node] = field(default_factory=list)


@dataclass(eq=False)
class List(BlockNode):
    ordered: bool = False
    start: int = 1
    items: list[ListItem] = field(default_factory=list)
    marker_style: str = "arabic"  # "arabic" | "lower-alpha-ru" | "bullet"
    # Литеральный разделитель маркера для arabic-списков: ``"."`` (`1.`) или
    # ``")"`` (`1)`). Источник истины — md, перетирает ``numbered_format`` из
    # конфига. Для bullet/alpha — игнорируется.
    delimiter: str = "."


@dataclass(eq=False)
class TemplateBlock(BlockNode):
    """Container ``::: {.template name=...}`` with optional YAML parameters."""

    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False)
class PageBreak(BlockNode):
    pass


@dataclass(eq=False)
class ThematicBreak(BlockNode):
    pass


@dataclass(eq=False)
class Mermaid(BlockNode):
    code: str = ""


@dataclass(eq=False)
class Document(Node):
    children: list[BlockNode] = field(default_factory=list)
