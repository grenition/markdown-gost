"""Юнит-тесты для :class:`markdown_gost.render.render_index.RenderIndex` (T016).

Проверяем:
- API сбора заголовков и нумерованных объектов;
- стабильность якорей (детерминированы по входу, уникальны между разными);
- независимость категорий ``image``/``table``/``listing``/``equation``.
"""

from __future__ import annotations

from markdown_gost.render.render_index import (
    HeadingEntry,
    ObjectEntry,
    RenderIndex,
)


def test_empty_index_has_no_entries() -> None:
    index = RenderIndex()
    assert index.headings == []
    assert index.numbered_objects == {}
    assert index.total_pages == 0


def test_add_heading_returns_entry_with_anchor_and_page() -> None:
    index = RenderIndex()
    entry = index.add_heading(
        level=1, text="ВВЕДЕНИЕ", numbered=True, number="1", page=1
    )
    assert isinstance(entry, HeadingEntry)
    assert entry.level == 1
    assert entry.text == "ВВЕДЕНИЕ"
    assert entry.numbered is True
    assert entry.number == "1"
    assert entry.page == 1
    assert entry.anchor  # непустой
    assert index.headings == [entry]


def test_add_unnumbered_heading_has_none_number() -> None:
    index = RenderIndex()
    entry = index.add_heading(
        level=1, text="СОДЕРЖАНИЕ", numbered=False, number=None, page=2
    )
    assert entry.numbered is False
    assert entry.number is None


def test_add_object_groups_by_category() -> None:
    index = RenderIndex()
    img = index.add_object(category="image", number=1, caption="Схема", page=3)
    tbl = index.add_object(category="table", number=1, caption="Параметры", page=4)
    img2 = index.add_object(category="image", number=2, caption=None, page=5)

    assert isinstance(img, ObjectEntry)
    assert img.number == 1
    assert img.caption == "Схема"
    assert img.page == 3
    assert img.anchor

    # независимые потоки нумерации, разные ключи в dict
    assert list(index.numbered_objects.keys()) == ["image", "table"]
    assert index.numbered_objects["image"] == [img, img2]
    assert index.numbered_objects["table"] == [tbl]


def test_object_with_none_caption_keeps_none() -> None:
    index = RenderIndex()
    entry = index.add_object(category="equation", number=1, caption=None, page=1)
    assert entry.caption is None


def test_anchors_are_unique_within_index() -> None:
    index = RenderIndex()
    a = index.add_heading(level=1, text="Глава", numbered=True, number="1", page=1)
    b = index.add_heading(level=1, text="Глава", numbered=True, number="2", page=2)
    c = index.add_object(category="image", number=1, caption="Глава", page=1)
    anchors = {a.anchor, b.anchor, c.anchor}
    assert len(anchors) == 3


def test_anchors_are_deterministic_across_runs() -> None:
    """Один и тот же набор входов → один и тот же набор якорей.

    Это гарантирует стабильность ссылок в DOCX/HTML между прогонами и
    воспроизводимость рендера.
    """

    def build() -> tuple[str, str]:
        idx = RenderIndex()
        h = idx.add_heading(
            level=2, text="Цели", numbered=True, number="1.1", page=1
        )
        o = idx.add_object(
            category="table", number=2, caption="Состав", page=4
        )
        return h.anchor, o.anchor

    first = build()
    second = build()
    assert first == second


def test_total_pages_is_settable() -> None:
    index = RenderIndex()
    index.set_total_pages(7)
    assert index.total_pages == 7


def test_anchor_is_valid_bookmark_name() -> None:
    """В Word ``w:bookmarkStart/@w:name`` не любит пробелы / спецсимволы.

    Якоря должны быть похожи на идентификатор: ASCII-буквы/цифры/подчёркивания.
    """

    index = RenderIndex()
    entry = index.add_heading(
        level=1,
        text="Очень длинный текст с пробелами, кириллицей и пунктуацией!",
        numbered=True,
        number="1",
        page=1,
    )
    anchor = entry.anchor
    assert anchor.replace("_", "").isalnum(), (
        f"anchor {anchor!r} must be alphanumeric/underscore"
    )
