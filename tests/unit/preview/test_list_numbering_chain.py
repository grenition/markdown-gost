"""Native list numbering chains: preview mirrors DOCX numbering.xml semantics.

DOCX (``renderable/list.py`` + ``renderable/numbering.py``): каждый корень
цепочки получает свежий ``abstractNum`` — счётчик живёт в пределах цепочки
(корень + его вложенные продолжения того же вида), соседние списки
начинаются заново. ``start != 1`` корня — ``w:start`` уровня; у вложенного
узла цепочки — ``startOverride``. Буквальные номера пунктов внутри списка
игнорируются (позиционная нумерация).
"""

from __future__ import annotations

from unittest.mock import patch

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.preview import build_preview_model
from markdown_gost.preview.builder import _PreviewBuilder
from markdown_gost.storage.fs import FilesystemStorage


def _config(overrides: str = "") -> Config:
    return load_config_from_string(f"preset: gost-7-32-2017\n{overrides}")


def _markers(markdown: str, cfg: Config | None = None) -> list[str]:
    model = build_preview_model(markdown, cfg or _config())
    return [
        block.marker
        for page in model.pages
        for block in page.blocks
        if block.kind == "list_item" and not block.continuation
    ]


def test_native_sibling_lists_restart_after_paragraph() -> None:
    assert _markers("1. A\n2. B\n\nТекст между\n\n1. C\n2. D\n") == ["1.", "2.", "1.", "2."]


def test_native_literal_start_of_root_is_honored() -> None:
    markdown = "1. A\n2. B\n\nТекст\n\n5. C\n6. D\n\nТекст\n\n1. E\n"

    assert _markers(markdown) == ["1.", "2.", "5.", "6.", "1."]


def test_native_mid_jump_numbers_items_positionally() -> None:
    # Буквальный «5.» внутри уже начатого списка игнорируется (как в DOCX).
    assert _markers("1. A\n2. B\n\n5. C\n6. D\n") == ["1.", "2.", "3.", "4."]


def test_native_lists_after_fenced_code_restart() -> None:
    markdown = "1. A\n2. B\n\n```\n1. fake\n2. fake\n```\n\n1. C\n2. D\n"

    assert _markers(markdown) == ["1.", "2.", "1.", "2."]


def test_native_nested_literal_start_overrides_chain_level() -> None:
    # marko поглощает indented «5.» в родительский пункт — строим AST руками
    # и проверяем гарантию уровня рендера: startOverride вложенного узла
    # уже начатой цепочки (счётчик уровня = start − 1, дальше позиционно).
    document = ast.Document(
        children=[
            ast.List(
                ordered=True,
                start=1,
                marker_style="arabic",
                delimiter=".",
                items=[
                    ast.ListItem(
                        children=[
                            ast.Paragraph(children=[ast.Text(text="A")]),
                            ast.List(
                                ordered=True,
                                start=5,
                                marker_style="arabic",
                                delimiter=".",
                                items=[
                                    ast.ListItem(
                                        children=[ast.Paragraph(children=[ast.Text(text="X")])]
                                    ),
                                    ast.ListItem(
                                        children=[ast.Paragraph(children=[ast.Text(text="Y")])]
                                    ),
                                ],
                            ),
                        ]
                    ),
                    ast.ListItem(children=[ast.Paragraph(children=[ast.Text(text="B")])]),
                ],
            )
        ]
    )
    builder = _PreviewBuilder(config=_config(), storage=FilesystemStorage())
    with patch("markdown_gost.preview.builder.parse", return_value=document):
        model = builder.build("")
    markers = [
        block.marker
        for page in model.pages
        for block in page.blocks
        if block.kind == "list_item" and not block.continuation
    ]
    assert markers == ["1.", "1.5.", "1.6.", "2."]


def test_native_nested_path_within_one_list() -> None:
    markdown = "1. A\n2. B\n    1. B1\n    2. B2\n3. C\n"

    assert _markers(markdown) == ["1.", "2.", "2.1.", "2.2.", "3."]


def test_native_second_sublist_under_same_parent_continues_level() -> None:
    markdown = "1. A\n    1. X\n\n   Продолжение пункта\n\n    1. Y\n2. B\n"

    assert _markers(markdown) == ["1.", "1.1.", "1.2.", "2."]


def test_native_arabic_under_bullet_is_fresh_hierarchical_chain() -> None:
    markdown = "- A\n    1. X\n        1. X1\n    2. Y\n- B\n"

    assert _markers(markdown) == ["—", "1.", "1.1.", "2.", "—"]


def test_native_bullet_nested_counters_restart_per_root() -> None:
    markdown = "- A\n    - x\n    - y\n\nТекст\n\n- B\n    - z\n"

    assert _markers(markdown) == ["—", "1)", "2)", "—", "1)"]


def test_inline_mode_restarts_numbering_per_list() -> None:
    cfg = _config("overrides:\n  lists:\n    mode: inline\n")

    markdown = "1. A\n2. B\n\nТекст\n\n1. C\n2. D\n"

    assert _markers(markdown, cfg) == ["1.", "2.", "1.", "2."]


def test_inline_mode_keeps_flat_markers_under_bullet() -> None:
    cfg = _config("overrides:\n  lists:\n    mode: inline\n")

    markdown = "- A\n    1. X\n        1. X1\n- B\n"

    assert _markers(markdown, cfg) == ["—", "1.", "1.", "—"]
