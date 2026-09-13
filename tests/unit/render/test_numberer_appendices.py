from __future__ import annotations

from markdown_gost.render.numberer import Numberer


def test_appendix_letters_skip_forbidden_russian_letters() -> None:
    n = Numberer()

    letters = [n.start_appendix() for _ in range(10)]

    assert letters == ["А", "Б", "В", "Г", "Д", "Е", "Ж", "И", "К", "Л"]


def test_appendix_resets_object_numbers_and_formats_display_numbers() -> None:
    n = Numberer()
    assert n.allocate("image") == 1

    n.start_appendix("А")

    assert n.allocate("image") == 1
    assert n.format_number("image", 1) == "А.1"


def test_appendix_heading_prefixes_are_letter_scoped() -> None:
    n = Numberer()

    n.start_appendix("А")
    assert n.bump_heading(1) == "А.1"
    assert n.bump_heading(2) == "А.1.1"

    n.start_appendix("Б")
    assert n.bump_heading(1) == "Б.1"
