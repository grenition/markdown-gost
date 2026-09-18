"""Unit tests for packaged preset discovery (available_presets)."""

from __future__ import annotations

from markdown_gost.config.presets import available_presets


def test_available_presets_lists_packaged_presets() -> None:
    assert available_presets() == ("gost-7-32-2017",)


def test_available_presets_are_sorted() -> None:
    presets = available_presets()
    assert presets == tuple(sorted(presets))
