"""Юнит-тесты парсера атрибутов изображений (``{width=... height=...}``)."""

from __future__ import annotations

import pytest

from markdown_gost.core.parser.attrs import (
    parse_image_attrs,
    parse_quoted_attrs,
    parse_size_list,
    parse_size_value,
    split_caption_attrs_block,
)


def test_parse_size_value_percent():
    assert parse_size_value("80%") == (80.0, "%")


def test_parse_size_value_cm():
    assert parse_size_value("10cm") == (10.0, "cm")


def test_parse_size_value_decimal():
    assert parse_size_value("12.5pt") == (12.5, "pt")


def test_parse_size_value_inches():
    assert parse_size_value("2in") == (2.0, "in")


def test_parse_size_value_px():
    assert parse_size_value("96px") == (96.0, "px")


def test_parse_size_value_mm():
    assert parse_size_value("100mm") == (100.0, "mm")


def test_parse_size_value_auto():
    assert parse_size_value("auto") == (0.0, "auto")


def test_parse_size_value_invalid_unit():
    assert parse_size_value("10rem") is None


def test_parse_size_value_no_unit():
    assert parse_size_value("10") is None


def test_parse_size_value_garbage():
    assert parse_size_value("abc") is None


def test_parse_size_value_negative_not_supported():
    # Отрицательные размеры — невалидны (для картинки бессмысленны).
    assert parse_size_value("-5cm") is None


def test_parse_image_attrs_only_width():
    width, height = parse_image_attrs("{width=80%}")
    assert width == (80.0, "%")
    assert height is None


def test_parse_image_attrs_only_height():
    width, height = parse_image_attrs("{height=10cm}")
    assert width is None
    assert height == (10.0, "cm")


def test_parse_image_attrs_both():
    width, height = parse_image_attrs("{width=10cm height=auto}")
    assert width == (10.0, "cm")
    assert height == (0.0, "auto")


def test_parse_image_attrs_with_comma_separator():
    # pandoc допускает ``key=value, key2=value2``; точно так же должны парситься.
    width, height = parse_image_attrs("{width=50%, height=200pt}")
    assert width == (50.0, "%")
    assert height == (200.0, "pt")


def test_parse_image_attrs_no_braces():
    width, height = parse_image_attrs("width=80% height=auto")
    assert width == (80.0, "%")
    assert height == (0.0, "auto")


def test_parse_image_attrs_empty_block():
    assert parse_image_attrs("{}") == (None, None)


def test_parse_image_attrs_invalid_value_skipped():
    width, height = parse_image_attrs("{width=10rem height=20cm}")
    assert width is None
    assert height == (20.0, "cm")


def test_parse_image_attrs_unknown_key_ignored():
    width, height = parse_image_attrs("{margin=10cm width=50%}")
    assert width == (50.0, "%")
    assert height is None


# ---- caption / table attrs ------------------------------------------------


def test_split_caption_attrs_no_block():
    text, attrs = split_caption_attrs_block("Список продуктов")
    assert text == "Список продуктов"
    assert attrs == {}


def test_split_caption_attrs_with_block():
    text, attrs = split_caption_attrs_block('Список продуктов {widths="20%, 30%, 50%"}')
    assert text == "Список продуктов"
    assert attrs == {"widths": "20%, 30%, 50%"}


def test_split_caption_attrs_multiple_keys():
    text, attrs = split_caption_attrs_block(
        'Caption {widths="6cm, auto, auto" heights="auto, 1cm, 1cm"}'
    )
    assert text == "Caption"
    assert attrs == {
        "widths": "6cm, auto, auto",
        "heights": "auto, 1cm, 1cm",
    }


def test_split_caption_attrs_empty_text():
    text, attrs = split_caption_attrs_block('{widths="5cm, 5cm"}')
    assert text == ""
    assert attrs == {"widths": "5cm, 5cm"}


def test_parse_quoted_attrs_block_form():
    assert parse_quoted_attrs('{a="1" b="2"}') == {"a": "1", "b": "2"}


def test_parse_quoted_attrs_no_braces():
    assert parse_quoted_attrs('a="1" b="2"') == {"a": "1", "b": "2"}


def test_parse_size_list_basic():
    out = parse_size_list("20%, 30%, 50%", expected_count=3, allow_percent=True)
    assert out == [(20.0, "%"), (30.0, "%"), (50.0, "%")]


def test_parse_size_list_mixed():
    out = parse_size_list("6cm, auto, 2in", expected_count=3, allow_percent=True)
    assert out == [(6.0, "cm"), (0.0, "auto"), (2.0, "in")]


def test_parse_size_list_count_mismatch_raises():
    with pytest.raises(ValueError, match="expected 3 values, got 2"):
        parse_size_list("20%, 30%", expected_count=3, allow_percent=True)


def test_parse_size_list_invalid_value_raises():
    with pytest.raises(ValueError, match="invalid size"):
        parse_size_list("20%, foo, 50%", expected_count=3, allow_percent=True)


def test_parse_size_list_percent_disallowed_raises():
    with pytest.raises(ValueError, match="percent values are not allowed"):
        parse_size_list(
            "1cm, 50%, 1cm", expected_count=3, allow_percent=False, field_name="heights"
        )
