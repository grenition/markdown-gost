from markdown_gost.config.schema import Config
from markdown_gost.core import ast
from markdown_gost.core.parser import parse, walk
from markdown_gost.render.references import prepare_document


def test_forward_references_share_numbering_with_appendix_scopes():
    document = prepare_document(
        parse(
            "См. [](#main), [](#table), [](#app), [](#eq), [](#end).\n\n"
            "# Метод {#main}\n\n"
            "| A |\n|---|\n| 1 |\n\n: Данные {#table}\n\n"
            "# Материалы {.appendix #app}\n\n"
            "$$x=1$$\n{#eq}\n\n# Итоги {#end}\n"
        ),
        Config(preset="default"),
    )
    paragraph = document.children[0]
    links = [node for node in paragraph.children if isinstance(node, ast.Link)]
    assert [link.children[0].text for link in links] == [
        "Раздел 1",
        "Таблица 1",
        "Приложение А",
        "Формула (А.1)",
        "Раздел 2",
    ]
    assert not any(isinstance(node, ast.Reference) for node in walk(document))


def test_missing_automatic_reference_fails():
    import pytest

    with pytest.raises(ValueError, match="missing"):
        prepare_document(parse("[](#missing)"), Config(preset="default"))
