from __future__ import annotations

from markdown_gost.render.numberer import Numberer


def test_get_without_save_returns_zero() -> None:
    numberer = Numberer()
    assert numberer.get_current_number("figure") == 0
    assert numberer.get_current_number("table") == 0


def test_allocate_returns_sequential_numbers() -> None:
    numberer = Numberer()
    assert numberer.allocate("figure") == 1
    assert numberer.allocate("figure") == 2
    assert numberer.allocate("figure") == 3
    assert numberer.get_current_number("figure") == 3


def test_categories_are_independent() -> None:
    numberer = Numberer()
    assert numberer.allocate("figure") == 1
    assert numberer.allocate("table") == 1
    assert numberer.allocate("figure") == 2
    assert numberer.allocate("listing") == 1
    assert numberer.get_current_number("figure") == 2
    assert numberer.get_current_number("table") == 1
    assert numberer.get_current_number("listing") == 1


def test_save_number_overwrites() -> None:
    numberer = Numberer()
    numberer.allocate("figure")
    numberer.allocate("figure")
    numberer.save_number("figure", 42)
    assert numberer.get_current_number("figure") == 42
    assert numberer.allocate("figure") == 43
