import pytest

from markdown_gost.core import ast
from markdown_gost.core.parser import parse
from markdown_gost.import_.postprocessor.caption_folder import transform


@pytest.mark.parametrize(
    "block,label",
    [
        ("| A |\n|---|\n| 1 |", "Таблица"),
        ("```python\nprint(1)\n```", "Листинг"),
    ],
)
@pytest.mark.parametrize("before", [True, False])
def test_import_emits_trailing_universal_caption(block, label, before):
    caption = f"{label} 12 — Пример"
    source = f"{caption}\n\n{block}" if before else f"{block}\n\n{caption}"
    result = "\n".join(transform(source.splitlines(), {}))
    assert ": Пример" in result
    assert result.index(": Пример") > result.index(block)
    assert isinstance(parse(result).children[0], ast.Caption)


def test_caption_like_code_is_preserved():
    source = "```text\nТаблица 1 — Буквальная строка\n| A |\n|---|\n```"
    assert "\n".join(transform(source.splitlines(), {})) == source
