from markdown_gost.config.schema import Config
from markdown_gost.preview.builder import build_preview_model


def test_preview_supports_references_sources_and_appendix_scope():
    model = build_preview_model(
        "См. [](#data) и [@book].\n\n"
        "# Метод\n\n# Данные {.appendix #data}\n\n## Значения\n\n"
        "$$x=1$$\n\n# Итоги\n\n"
        "::: {.bibliography}\n- id: book\n  text: Учебник\n:::\n",
        Config(preset="gost-7-32-2017"),
    )
    blocks = [block for page in model.pages for block in page.blocks]
    assert blocks[0].text == "См. Приложение А и [1]."
    assert any(block.id == "data" for block in blocks)
    assert any(block.number == "А.1" for block in blocks)
    assert any(block.text == "Итоги" and block.number == "2" for block in blocks)
    assert any("Учебник" in block.text for block in blocks)


def test_preview_custom_ids_and_thematic_break():
    model = build_preview_model(
        "# Метод {#method}\n\n| A |\n|---|\n| 1 |\n\n: Данные {#data}\n\n---\n",
        Config(preset="gost-7-32-2017"),
    )
    blocks = [block for page in model.pages for block in page.blocks]
    assert {"method", "data"} <= {block.id for block in blocks}
    assert blocks[-1].kind == "thematic_break"
