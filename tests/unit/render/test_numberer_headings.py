"""Юнит-тесты для многоуровневой нумерации заголовков в Numberer."""

from __future__ import annotations

import pytest

from markdown_gost.render.numberer import Numberer


def test_first_h1_is_one():
    n = Numberer()
    assert n.bump_heading(1) == "1"


def test_h1_h2_h3_h2_h1():
    n = Numberer()
    assert n.bump_heading(1) == "1"
    assert n.bump_heading(2) == "1.1"
    assert n.bump_heading(3) == "1.1.1"
    assert n.bump_heading(2) == "1.2"
    assert n.bump_heading(1) == "2"
    assert n.bump_heading(2) == "2.1"


def test_skipped_h1_does_not_break():
    """Если первый заголовок — h2, ведёт себя как «0.1»."""
    n = Numberer()
    assert n.bump_heading(2) == "0.1"


def test_invalid_level_raises():
    n = Numberer()
    with pytest.raises(ValueError):
        n.bump_heading(0)
    with pytest.raises(ValueError):
        n.bump_heading(7)


def test_heading_prefix_at_returns_state_without_bump():
    n = Numberer()
    n.bump_heading(1)
    n.bump_heading(2)
    assert n.heading_prefix_at(1) == "1"
    assert n.heading_prefix_at(2) == "1.1"
    # Состояние не сдвинулось.
    assert n.bump_heading(2) == "1.2"
