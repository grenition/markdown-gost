from __future__ import annotations

from docx.oxml.ns import qn
from docx.shared import Cm

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.bibliography import BibliographyIndex
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.renderable.base import RenderedInfo
from markdown_gost.renderable.bibliography import Bibliography
from markdown_gost.renderable.paragraph import Paragraph


def _config(yaml: str = "preset: default\n"):
    return load_config_from_string(yaml)


def _source(source_id: str, **fields: object) -> ast.BibliographySource:
    return ast.BibliographySource(id=source_id, fields=dict(fields))


def _index(cfg, sources: list[ast.BibliographySource]) -> BibliographyIndex:
    return BibliographyIndex.from_document(
        ast.Document(children=[ast.Bibliography(sources=sources)]),
        cfg,
    )


def test_paragraph_renders_citation_number() -> None:
    cfg = _config()
    document = build_document(cfg)
    index = _index(cfg, [_source("book", title="Book")])
    paragraph = Paragraph(document, cfg, bibliography=index)

    paragraph.add_inline_nodes([ast.Text(text="См. "), ast.Citation(key="book")])

    assert paragraph.docx_paragraph.text == "См. [1]"


def test_paragraph_uses_configurable_citation_format() -> None:
    cfg = _config(
        "preset: default\n"
        "overrides:\n"
        "  bibliography:\n"
        "    citation_format: \"({n})\"\n"
    )
    document = build_document(cfg)
    index = _index(cfg, [_source("book", title="Book")])
    paragraph = Paragraph(document, cfg, bibliography=index)

    paragraph.add_inline_nodes([ast.Citation(key="book")])

    assert paragraph.docx_paragraph.text == "(1)"


def test_bibliography_entries_are_plain_paragraphs_with_marker() -> None:
    cfg = _config()
    document = build_document(cfg)
    source = _source("raw", text="ГОСТ 7.32-2017. Описание.")
    index = _index(cfg, [source])
    renderable = Bibliography(document, cfg, ast.Bibliography(sources=[source]), index)

    items = [
        item
        for item in renderable.render(
            None, LayoutState(max_height=Cm(20), max_width=Cm(15))
        )
        if isinstance(item, RenderedInfo)
    ]

    assert len(items) == 1
    paragraph = items[0].docx_element
    assert paragraph.text == "1. ГОСТ 7.32-2017. Описание."
    assert paragraph.paragraph_format.first_line_indent is not None
    assert paragraph._p.find(qn("w:pPr") + "/" + qn("w:numPr")) is None
    assert paragraph._p.find(f".//{qn('w:noBreakHyphen')}") is None


def test_bibliography_entry_number_format_is_configurable() -> None:
    cfg = _config(
        "preset: default\n"
        "overrides:\n"
        "  bibliography:\n"
        "    entry_number_format: \"[{n}]\"\n"
    )
    document = build_document(cfg)
    source = _source("raw", text="Raw text")
    index = _index(cfg, [source])
    renderable = Bibliography(document, cfg, ast.Bibliography(sources=[source]), index)

    items = [
        item
        for item in renderable.render(
            None, LayoutState(max_height=Cm(20), max_width=Cm(15))
        )
        if isinstance(item, RenderedInfo)
    ]

    assert items[0].docx_element.text == "[1] Raw text"
