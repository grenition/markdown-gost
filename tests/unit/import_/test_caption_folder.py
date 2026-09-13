"""Unit tests for the caption folder (T033).

Folds ``Таблица/Рисунок/Листинг N — Caption`` paragraphs adjacent to the
captioned block into our extended-markdown directives.
"""

from __future__ import annotations

from markdown_gost.import_.postprocessor import caption_folder


def _run(text: str) -> str:
    return "\n".join(caption_folder.transform(text.split("\n"), {}))


def test_caption_before_table_becomes_directive() -> None:
    src = "Таблица 1 — Продукты\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    expected = "| A | B |\n|---|---|\n| 1 | 2 |\n\n: Продукты"
    assert _run(src) == expected


def test_caption_after_table_stays_after_it() -> None:
    src = "| A | B |\n|---|---|\n| 1 | 2 |\n\nТаблица 1. Продукты"
    expected = "| A | B |\n|---|---|\n| 1 | 2 |\n\n: Продукты"
    assert _run(src) == expected


def test_caption_before_image_rewrites_alt_and_drops_caption() -> None:
    src = "Рисунок 1 — Схема\n\n![](media/image1.png)"
    expected = "\n![Схема](media/image1.png)"
    assert _run(src) == expected


def test_ris_abbreviation_supported() -> None:
    src = "Рис. 2.1 — Карта\n\n![](map.png)"
    expected = "\n![Карта](map.png)"
    assert _run(src) == expected


def test_listing_caption_becomes_directive() -> None:
    src = "Листинг 1 — Merge sort\n\n```python\nprint(1)\n```"
    expected = "```python\nprint(1)\n```\n\n: Merge sort"
    assert _run(src) == expected


def test_caption_with_no_adjacent_block_is_left_alone() -> None:
    src = "Some prose.\n\nТаблица 1 — Orphan caption\n\nMore prose."
    assert _run(src) == src


def test_caption_too_far_from_block_is_not_folded() -> None:
    # 3 blank lines between caption and block exceeds the 2-line gap.
    src = "Таблица 1 — Foo\n\n\n\n| A |\n|---|\n| 1 |"
    assert _run(src) == src
