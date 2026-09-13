"""Интеграционные тесты двухпроходного рендера (T016).

Сценарий:
1. Документ из заголовков + одной нумерованной картинки.
2. После ``Renderer.process(...)`` смотрим в ``renderer.index``:
   - заголовки попали в ``headings`` с правильными ``page``/``number``/``text``;
   - картинка попала в ``numbered_objects['image']``;
   - ``total_pages`` — фактическое число страниц;
   - на параграф заголовка повешена закладка с тем же ``anchor``.
3. Стаб-renderable, который в ``post_process`` подставляет ``total_pages``
   в плейсхолдер ``{TOTAL}`` своего параграфа — проверяем замену.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from docx.oxml.ns import qn
from docx.shared import Cm, Length

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.render_index import RenderIndex
from markdown_gost.render.renderer import Renderer
from markdown_gost.renderable._oxml import create_element
from markdown_gost.renderable.base import Renderable, RenderedInfo, SubRenderable
from markdown_gost.renderable.heading import Heading


def _config():
    return load_config_from_string("preset: default\n")


def test_renderer_collects_headings_into_index() -> None:
    cfg = _config()
    document = build_document(cfg)
    numberer = Numberer()
    h1 = Heading(
        document,
        cfg,
        ast.Heading(level=1, numbered=True, children=[ast.Text(text="ВВЕДЕНИЕ")]),
        numberer,
    )
    h2 = Heading(
        document,
        cfg,
        ast.Heading(level=2, numbered=True, children=[ast.Text(text="Цели")]),
        numberer,
    )
    h_unn = Heading(
        document,
        cfg,
        ast.Heading(level=1, numbered=False, children=[ast.Text(text="СОДЕРЖАНИЕ")]),
        numberer,
    )
    renderer = Renderer(document)
    renderer.process([h1, h2, h_unn])

    headings = renderer.index.headings
    assert [h.text for h in headings] == ["ВВЕДЕНИЕ", "Цели", "СОДЕРЖАНИЕ"]
    assert [h.numbered for h in headings] == [True, True, False]
    assert [h.number for h in headings] == ["1", "1.1", None]
    assert [h.level for h in headings] == [1, 2, 1]
    # Все попали на 1-ю или 2-ю страницу (тривиальный документ).
    for h in headings:
        assert h.page >= 1
    # Якоря уникальны.
    anchors = {h.anchor for h in headings}
    assert len(anchors) == len(headings)


def test_renderer_index_has_total_pages_after_process() -> None:
    cfg = _config()
    document = build_document(cfg)
    renderer = Renderer(document)
    renderer.process([])
    assert renderer.index.total_pages >= 1


def test_heading_paragraph_gets_bookmark_with_anchor() -> None:
    """Anchor → ``<w:bookmarkStart w:name="...">`` на параграфе заголовка."""

    cfg = _config()
    document = build_document(cfg)
    numberer = Numberer()
    h = Heading(
        document,
        cfg,
        ast.Heading(level=1, numbered=True, children=[ast.Text(text="ВВЕДЕНИЕ")]),
        numberer,
    )
    renderer = Renderer(document)
    renderer.process([h])

    entry = renderer.index.headings[0]

    # Ищем bookmarkStart с правильным именем где-то в body.
    body = document.element.body
    bookmarks = body.findall(f".//{qn('w:bookmarkStart')}")
    names = [bm.get(qn("w:name")) for bm in bookmarks]
    assert entry.anchor in names, f"expected anchor {entry.anchor!r} in {names!r}"


class _PageCountStub(Renderable):
    """Стаб: рендерит «{TOTAL}» в первом проходе, в post_process заменяет
    его на фактическое число страниц.
    """

    def __init__(self, document: Any) -> None:
        from docx.text.paragraph import Paragraph as DocxParagraph

        self._document = document
        self._paragraph = DocxParagraph(create_element("w:p"), document)
        self._paragraph.add_run("{TOTAL}")

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        # Высоту берём фиксированную — для теста хватит 14pt.
        from docx.shared import Pt

        height = Length(int(Pt(14)))
        yield RenderedInfo(self._paragraph, height)
        layout_state.add_height(height)

    def post_process(self, index: RenderIndex, document: Any) -> None:  # type: ignore[override]
        # Заменяем «{TOTAL}» во всех runs параграфа на index.total_pages.
        for run in self._paragraph.runs:
            if "{TOTAL}" in run.text:
                run.text = run.text.replace("{TOTAL}", str(index.total_pages))


def test_post_process_can_substitute_total_pages() -> None:
    cfg = _config()
    document = build_document(cfg)
    stub = _PageCountStub(document)
    renderer = Renderer(document)
    renderer.process([stub])

    # После двухпроходного рендера {TOTAL} должно быть заменено числом.
    text = stub._paragraph.text
    assert "{TOTAL}" not in text, f"placeholder not replaced, got {text!r}"
    assert text.isdigit(), f"expected digit string, got {text!r}"
    assert int(text) == renderer.index.total_pages


def test_image_renderable_added_to_numbered_objects(tmp_path) -> None:
    """Картинка из storage → в ``index.numbered_objects['image']``."""

    import base64

    from markdown_gost.renderable.image import Image
    from markdown_gost.storage.fs import FilesystemStorage

    # Минимальный валидный PNG (1×1 прозрачный) — берём bytes.

    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8"
        "AAAAASUVORK5CYII="
    )
    img_path = tmp_path / "tiny.png"
    img_path.write_bytes(png_bytes)

    cfg = _config()
    document = build_document(cfg)
    storage = FilesystemStorage(base_dir=tmp_path)

    img_node = ast.Image(src="tiny.png", alt="Маленькая схема")
    image = Image(document, cfg, img_node, storage)

    renderer = Renderer(document)
    renderer.process([image])

    images = renderer.index.numbered_objects.get("image", [])
    assert len(images) == 1
    entry = images[0]
    assert entry.number == 1
    assert entry.caption == "Маленькая схема"
    assert entry.page >= 1
    assert entry.anchor


def test_total_pages_reflects_actual_layout() -> None:
    """Если контент явно превышает одну страницу, ``total_pages`` >= 2."""

    cfg = _config()
    document = build_document(cfg)
    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(1.5)

    big = _BigBlockRenderable(document, height=Cm(20))
    small = _BigBlockRenderable(document, height=Cm(10))
    renderer = Renderer(document)
    renderer.process([big, small])

    # 20cm + 10cm > содержимое A4 (29.7 - 4 = 25.7cm) → как минимум 2 страницы.
    assert renderer.index.total_pages >= 2


class _BigBlockRenderable(Renderable):
    def __init__(self, document: Any, height: Length) -> None:
        from docx.text.paragraph import Paragraph as DocxParagraph

        self._document = document
        self._height = height
        self._paragraph = DocxParagraph(create_element("w:p"), document)
        self._paragraph.add_run("block")

    def render(
        self,
        previous_rendered: RenderedInfo | None,
        layout_state: LayoutState,
    ) -> Generator[RenderedInfo | SubRenderable]:
        yield RenderedInfo(self._paragraph, self._height)
        layout_state.add_height(self._height)
