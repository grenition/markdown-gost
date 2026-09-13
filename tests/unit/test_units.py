"""Юнит-тесты парсера длин из строки."""

from __future__ import annotations

import pytest
from docx.shared import Cm, Inches, Mm, Pt

from markdown_gost.config.units import parse_length, parse_pt


def test_parse_cm():
    assert abs(parse_length("2cm") - Cm(2)) <= 1


def test_parse_mm():
    assert abs(parse_length("15mm") - Mm(15)) <= 1


def test_parse_pt():
    assert abs(parse_length("14pt") - Pt(14)) <= 1


def test_parse_in():
    assert abs(parse_length("1in") - Inches(1)) <= 1


def test_parse_zero():
    assert parse_length("0pt") == 0


def test_parse_decimal():
    assert abs(parse_length("1.25cm") - Cm(1.25)) <= 1


def test_parse_pt_helper():
    assert parse_pt("14pt") == pytest.approx(14.0, rel=1e-3)


def test_parse_pt_bare_number():
    assert parse_pt("10") == pytest.approx(10.0, rel=1e-3)
    assert parse_pt(" 12.5 ") == pytest.approx(12.5, rel=1e-3)


def test_invalid_unit_raises():
    with pytest.raises(ValueError):
        parse_length("3km")


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_length("")


def test_non_string_raises():
    with pytest.raises(TypeError):
        parse_length(14)  # type: ignore[arg-type]
