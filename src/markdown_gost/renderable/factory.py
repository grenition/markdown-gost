"""AST → список :class:`Renderable`.

Поддерживает Paragraph/Heading/PageBreak/List/Image/Table (T012/T013) и
``TemplateBlock`` (T022) — последний делегирует в реестр шаблонов.
Остальные блочные узлы (Mermaid и т.п.) пока возвращаются как красная
stub-плашка.
"""

from __future__ import annotations

from docx.document import Document as DocxDocument

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.core.parser.attrs import parse_size_list
from markdown_gost.render.bibliography import BibliographyIndex
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.references import prepare_document
from markdown_gost.renderable.appendix import Appendix
from markdown_gost.renderable.base import Renderable
from markdown_gost.renderable.bibliography import Bibliography as BibliographyRenderable
from markdown_gost.renderable.equation import Equation
from markdown_gost.renderable.heading import Heading
from markdown_gost.renderable.image import Image
from markdown_gost.renderable.list import List
from markdown_gost.renderable.listing import Listing
from markdown_gost.renderable.page_break import PageBreak
from markdown_gost.renderable.paragraph import Paragraph
from markdown_gost.renderable.table import Table
from markdown_gost.storage.base import Storage
from markdown_gost.storage.fs import FilesystemStorage
from markdown_gost.templates import TemplateContext, render_template


class RenderableFactory:
    def __init__(
        self,
        document: DocxDocument,
        config: Config,
        numberer: Numberer,
        storage: Storage | None = None,
    ) -> None:
        self._document = document
        self._config = config
        self._numberer = numberer
        self._storage: Storage = storage if storage is not None else FilesystemStorage()
        # Полный AST документа — нужен шаблонам, которым важен глобальный план
        # (например, ``content`` сканирует все ``ast.Heading`` заранее, чтобы
        # зарезервировать высоту под TOC). Заполняется в ``create_all``.
        self._document_ast: ast.Document = ast.Document()
        self._bibliography_index = BibliographyIndex.from_document(self._document_ast, self._config)

    def create_all(self, document_ast: ast.Document) -> list[Renderable]:
        document_ast = prepare_document(document_ast, self._config)
        self._document_ast = document_ast
        self._bibliography_index = BibliographyIndex.from_document(document_ast, self._config)
        out: list[Renderable] = []
        children = document_ast.children
        i = 0
        while i < len(children):
            child = children[i]
            # Нормализованная подпись → следующий ast.Table должен быть подхвачен
            # вместе с подписью и атрибутами в одну Table renderable.
            if (
                isinstance(child, ast.Caption)
                and child.target == "table"
                and i + 1 < len(children)
                and isinstance(children[i + 1], ast.Table)
            ):
                next_table = children[i + 1]
                assert isinstance(next_table, ast.Table)
                rendered = self._create_table(next_table, child)
                rendered.identifier = next_table.identifier
                out.append(rendered)
                i += 2
                continue
            # Нормализованная подпись → следующий ast.Listing подхватываем
            # вместе с подписью в одну Listing renderable.
            if (
                isinstance(child, ast.Caption)
                and child.target == "listing"
                and i + 1 < len(children)
                and isinstance(children[i + 1], ast.Listing)
            ):
                next_listing = children[i + 1]
                assert isinstance(next_listing, ast.Listing)
                rendered_listing = self._create_listing(next_listing, child)
                rendered_listing.identifier = next_listing.identifier
                out.append(rendered_listing)
                i += 2
                continue
            renderable = self._create(child)
            if renderable is not None:
                image = (
                    _extract_standalone_image(child) if isinstance(child, ast.Paragraph) else None
                )
                renderable.identifier = image.identifier if image else child.identifier
                out.append(renderable)
            i += 1
        return out

    def _create(self, node: ast.BlockNode) -> Renderable | None:
        if isinstance(node, ast.AppendixEnd):
            self._numberer.end_appendix()
            from markdown_gost.renderable.appendix import AppendixEnd

            return AppendixEnd()
        if isinstance(node, ast.AppendixStart):
            return Appendix(self._document, self._config, node, self._numberer)
        if isinstance(node, ast.Heading):
            return Heading(self._document, self._config, node, self._numberer)
        if isinstance(node, ast.Paragraph):
            standalone_image = _extract_standalone_image(node)
            if standalone_image is not None:
                return Image(self._document, self._config, standalone_image, self._storage)
            paragraph = Paragraph(
                self._document,
                self._config,
                storage=self._storage,
                bibliography=self._bibliography_index,
            )
            paragraph.add_inline_nodes(node.children)
            return paragraph
        if isinstance(node, ast.PageBreak):
            return PageBreak(self._document)
        if isinstance(node, ast.ThematicBreak):
            from markdown_gost.renderable.thematic_break import ThematicBreak

            return ThematicBreak(self._document, self._config)
        if isinstance(node, ast.List):
            return List(
                self._document,
                self._config,
                node,
                bibliography=self._bibliography_index,
            )
        if isinstance(node, ast.Table):
            return self._create_table(node, caption=None)
        if isinstance(node, ast.Listing):
            return self._create_listing(node, caption=None)
        if isinstance(node, ast.Equation):
            return Equation(self._document, self._config, node)
        if isinstance(node, ast.Bibliography):
            return BibliographyRenderable(
                self._document,
                self._config,
                node,
                self._bibliography_index,
            )
        if isinstance(node, ast.TemplateBlock):
            ctx = TemplateContext(
                document=self._document,
                config=self._config,
                document_ast=self._document_ast,
            )
            return render_template(node.name, dict(node.params), ctx)
        if isinstance(node, ast.Caption):
            # Подпись без следующего за ней объекта — игнорируем (вряд ли
            # имеет визуальный смысл сама по себе; в будущем можно отдать
            # как обычный параграф).
            return None
        # Не поддерживаемые в T012 блоки — stub-плашка с указанием типа.
        return self._unsupported_stub(node)

    def _create_table(self, node: ast.Table, caption: ast.Caption | None) -> Table:
        caption_text: str | None = None
        column_widths: list[ast.Length] | None = node.column_widths
        row_heights: list[ast.Length] | None = node.row_heights
        if caption is not None:
            caption_text = caption.text
            ncols = max((len(row.cells) for row in node.rows), default=0)
            nrows = len(node.rows)
            raw_widths = caption.attrs.get("widths")
            if raw_widths:
                pairs = parse_size_list(
                    raw_widths,
                    expected_count=ncols,
                    allow_percent=True,
                    field_name="widths",
                )
                column_widths = [ast.Length(value=v, unit=u) for v, u in pairs]
            raw_heights = caption.attrs.get("heights")
            if raw_heights:
                pairs = parse_size_list(
                    raw_heights,
                    expected_count=nrows,
                    allow_percent=False,
                    field_name="heights",
                )
                row_heights = [ast.Length(value=v, unit=u) for v, u in pairs]
        return Table(
            self._document,
            self._config,
            node,
            caption_text=caption_text,
            column_widths=column_widths,
            row_heights=row_heights,
            storage=self._storage,
            bibliography=self._bibliography_index,
        )

    def _create_listing(self, node: ast.Listing, caption: ast.Caption | None) -> Listing:
        caption_text = caption.text if caption is not None else None
        return Listing(
            self._document,
            self._config,
            node,
            caption_text=caption_text,
        )

    def _unsupported_stub(self, node: ast.BlockNode) -> Renderable:
        type_name = type(node).__name__
        paragraph = Paragraph(self._document, self._config, bibliography=self._bibliography_index)
        paragraph.add_inline_nodes([ast.Text(text=f"<{type_name} not supported yet>")])
        return paragraph


def _extract_standalone_image(paragraph: ast.Paragraph) -> ast.Image | None:
    """Если в параграфе ровно одна картинка и нет другого видимого контента —
    вернуть её для рендера блочной ``Image`` с подписью.

    Текст из пробелов/мягких переносов считается «невидимым» — markdown часто
    оставляет их вокруг ``![](...)`` на отдельной строке.
    """

    image: ast.Image | None = None
    for child in paragraph.children:
        if isinstance(child, ast.Image):
            if image is not None:
                return None  # больше одной картинки → inline-режим
            image = child
            continue
        if isinstance(child, ast.Text) and not child.text.strip():
            continue
        if isinstance(child, ast.LineBreak):
            continue
        return None
    return image
