from __future__ import annotations

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.parser import parse
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.numberer import Numberer
from markdown_gost.render.renderer import Renderer
from markdown_gost.renderable.factory import RenderableFactory


def test_appendix_factory_and_renderer_keep_letters_in_sync() -> None:
    config = load_config_from_string("preset: default\n")
    document = build_document(config)
    ast_doc = parse(
        "# Исходные данные {.appendix}\n\n"
        "## Раздел приложения\n\n"
        "$$x=1$$\n\n"
        "# Расчеты {.appendix}\n\n"
        "## Второй раздел\n"
    )
    renderables = RenderableFactory(
        document, config, Numberer()
    ).create_all(ast_doc)

    renderer = Renderer(document)
    renderer.process(renderables)

    assert [h.text for h in renderer.index.headings] == [
        "ПРИЛОЖЕНИЕ А Исходные данные",
        "Раздел приложения",
        "ПРИЛОЖЕНИЕ Б Расчеты",
        "Второй раздел",
    ]
    assert [h.number for h in renderer.index.headings] == [
        None,
        "А.1",
        None,
        "Б.1",
    ]
    equation = renderer.index.numbered_objects["equation"][0]
    assert equation.number == 1
    assert equation.number_text == "А.1"
