"""Юнит-тесты на schema-поля spacing для блок-элементов (T013b).

Поля ``space_before`` и ``space_after`` появились в:
- ``Table`` — управление отступом до подписи и после таблицы
- ``Listing`` — wired в T014, schema-поля уже сейчас (zero-impact)
- ``CaptionStyle`` — для всех категорий captions (image/table/listing)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.config.schema import CaptionStyle, Equation, Listing, Table


class TestTableBlockSpacingDefaults:
    def test_table_space_before_default_is_zero(self) -> None:
        table = Table()
        assert table.space_before == "0pt"

    def test_table_space_after_default_is_zero(self) -> None:
        table = Table()
        assert table.space_after == "0pt"

    def test_table_space_before_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  table:\n    space_before: 6pt\n"
        )
        assert cfg.table.space_before == "6pt"

    def test_table_space_after_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  table:\n    space_after: 12pt\n"
        )
        assert cfg.table.space_after == "12pt"


class TestListingBlockSpacingDefaults:
    def test_listing_space_before_default_is_zero(self) -> None:
        listing = Listing()
        assert listing.space_before == "0pt"

    def test_listing_space_after_default_is_zero(self) -> None:
        listing = Listing()
        assert listing.space_after == "0pt"

    def test_listing_space_before_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  listing:\n    space_before: 6pt\n"
        )
        assert cfg.listing.space_before == "6pt"

    def test_listing_space_after_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  listing:\n    space_after: 12pt\n"
        )
        assert cfg.listing.space_after == "12pt"


class TestEquationBlockSpacingDefaults:
    def test_equation_space_before_default_is_zero(self) -> None:
        equation = Equation()
        assert equation.space_before == "0pt"

    def test_equation_space_after_default_is_zero(self) -> None:
        equation = Equation()
        assert equation.space_after == "0pt"

    def test_equation_space_before_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  equation:\n    space_before: 6pt\n"
        )
        assert cfg.equation.space_before == "6pt"

    def test_equation_space_after_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  equation:\n    space_after: 12pt\n"
        )
        assert cfg.equation.space_after == "12pt"

    @pytest.mark.parametrize("field", ["space_before", "space_after"])
    @pytest.mark.parametrize("value", ["not-a-length", "-1pt"])
    def test_equation_spacing_must_be_non_negative_length_string(
        self, field: str, value: str
    ) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string(
                "preset: default\n"
                "overrides:\n"
                "  equation:\n"
                f"    {field}: {value}\n"
            )


class TestCaptionStyleBlockSpacingDefaults:
    def test_caption_space_before_default_is_zero(self) -> None:
        cap = CaptionStyle()
        assert cap.space_before == "0pt"

    def test_caption_space_after_default_is_zero(self) -> None:
        cap = CaptionStyle()
        assert cap.space_after == "0pt"

    def test_caption_line_spacing_default_inherits_body(self) -> None:
        cap = CaptionStyle()
        assert cap.line_spacing is None

    def test_caption_image_space_before_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  captions:\n    image:\n      space_before: 6pt\n"
        )
        assert cfg.captions.image.space_before == "6pt"

    def test_caption_image_space_after_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  captions:\n    image:\n      space_after: 6pt\n"
        )
        assert cfg.captions.image.space_after == "6pt"

    def test_caption_image_line_spacing_override(self) -> None:
        cfg = load_config_from_string(
            "preset: default\noverrides:\n  captions:\n    image:\n      line_spacing: 1.0\n"
        )
        assert cfg.captions.image.line_spacing == 1.0

    @pytest.mark.parametrize("value", ["0", "-1"])
    def test_caption_line_spacing_must_be_positive(self, value: str) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string(
                "preset: default\n"
                "overrides:\n"
                "  captions:\n"
                "    image:\n"
                f"      line_spacing: {value}\n"
            )
