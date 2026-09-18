from pathlib import Path

import pytest
from pydantic import ValidationError

from markdown_gost.config.errors import UnknownPresetError
from markdown_gost.config.loader import load_config_from_path, load_config_from_string
from markdown_gost.config.schema import CaptionStyle, Config, HeadingLevel


class TestPresetLoading:
    def test_loads_default_preset_with_no_overrides(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")

        assert cfg.preset == "gost-7-32-2017"
        assert cfg.font.family == "Times New Roman"
        assert cfg.font.size == "14pt"
        assert cfg.page.size == "A4"

    def test_unknown_preset_raises_unknown_preset_error(self) -> None:
        with pytest.raises(UnknownPresetError):
            load_config_from_string("preset: nonexistent\n")

    def test_missing_preset_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string("font:\n  size: 12pt\n")

    def test_empty_yaml_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string("")

    def test_non_string_preset_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string("preset: 42\n")


class TestOverrides:
    def test_top_level_field_override_replaces_value(self) -> None:
        cfg = load_config_from_string(
            "preset: gost-7-32-2017\noverrides:\n  font:\n    size: 12pt\n"
        )

        assert cfg.font.size == "12pt"
        assert cfg.font.family == "Times New Roman"

    def test_nested_override_deep_merges_with_preset(self) -> None:
        cfg = load_config_from_string(
            "preset: gost-7-32-2017\noverrides:\n  page:\n    margins:\n      top: 3cm\n"
        )

        assert cfg.page.margins.top == "3cm"
        assert cfg.page.margins.left == "30mm"

    def test_unknown_field_in_overrides_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string(
                "preset: gost-7-32-2017\noverrides:\n  font:\n    nonexistent_field: x\n"
            )

    def test_invalid_value_type_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            load_config_from_string(
                "preset: gost-7-32-2017\noverrides:\n  font:\n    line_spacing: not-a-number\n"
            )

    def test_overrides_can_be_empty(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\noverrides: {}\n")
        assert cfg.preset == "gost-7-32-2017"

    def test_overrides_omitted_keeps_preset_defaults(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        assert cfg.lists.bullet_marker == "\u2014"

    def test_structural_heading_overrides_deep_merge(self) -> None:
        cfg = load_config_from_string(
            "preset: gost-7-32-2017\n"
            "overrides:\n"
            "  headings:\n"
            "    structural:\n"
            "      uppercase: false\n"
            "      alignment: left\n"
            "    structural_titles:\n"
            "      - АННОТАЦИЯ\n"
        )

        assert cfg.headings.structural.uppercase is False
        assert cfg.headings.structural.alignment == "left"
        assert cfg.headings.structural.bold is True
        assert cfg.headings.structural_titles == ["АННОТАЦИЯ"]


class TestFromPath:
    def test_loads_from_yaml_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "cfg.yaml"
        cfg_file.write_text(
            "preset: gost-7-32-2017\noverrides:\n  font:\n    size: 13pt\n",
            encoding="utf-8",
        )

        cfg = load_config_from_path(cfg_file)

        assert cfg.font.size == "13pt"

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config_from_path(tmp_path / "missing.yaml")


class TestDefaultPresetContent:
    def test_default_continuation_break_is_disabled(self) -> None:
        """Default-пресет не включает ручной разрез — Word/LO ломают сам.
        Пользователь поднимает тогглер ``captions.continuation_break`` явно,
        когда требуется подпись «Продолжение …» на стыке страниц."""
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        assert cfg.captions.continuation_break is False

    def test_default_image_caption_centered(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        assert cfg.captions.image.alignment == "center"

    def test_default_headings_have_at_least_three_levels(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        assert 1 in cfg.headings.levels
        assert 2 in cfg.headings.levels
        assert 3 in cfg.headings.levels

    def test_default_structural_headings_are_centered_uppercase(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        _assert_heading(
            cfg.headings.structural,
            size="14pt",
            bold=True,
            italic=False,
            uppercase=True,
            alignment="center",
            space_before="0pt",
            space_after="0pt",
            page_break_before=True,
            indent_first_line="0cm",
        )
        assert "ВВЕДЕНИЕ" in cfg.headings.structural_titles
        assert "ЗАКЛЮЧЕНИЕ" in cfg.headings.structural_titles

    def test_gost_page_geometry(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")
        assert cfg.page.margins.top == "20mm"
        assert cfg.page.margins.right == "15mm"
        assert cfg.page.margins.bottom == "20mm"
        assert cfg.page.margins.left == "30mm"
        assert cfg.paragraph.indent_first_line == "1.25cm"
        assert cfg.listing.font.size == "12pt"


def _assert_caption(
    caption: CaptionStyle,
    *,
    italic: bool,
    bold: bool,
    alignment: str,
    format: str,
    space_before: str,
    space_after: str,
    line_spacing: float | None,
) -> None:
    assert caption.italic is italic
    assert caption.bold is bold
    assert caption.alignment == alignment
    assert caption.format == format
    assert caption.space_before == space_before
    assert caption.space_after == space_after
    assert caption.line_spacing == line_spacing


def _assert_heading(
    heading: HeadingLevel,
    *,
    size: str,
    bold: bool,
    italic: bool,
    uppercase: bool,
    alignment: str,
    space_before: str,
    space_after: str,
    page_break_before: bool,
    indent_first_line: str,
) -> None:
    assert heading.size == size
    assert heading.bold is bold
    assert heading.italic is italic
    assert heading.uppercase is uppercase
    assert heading.alignment == alignment
    assert heading.space_before == space_before
    assert heading.space_after == space_after
    assert heading.page_break_before is page_break_before
    assert heading.keep_with_next is True
    assert heading.indent_first_line == indent_first_line


def _assert_common_body_config(
    cfg: Config,
    *,
    right_margin: str,
) -> None:
    assert cfg.page.size == "A4"
    assert cfg.page.orientation == "portrait"
    assert cfg.page.margins.top == "20mm"
    assert cfg.page.margins.right == right_margin
    assert cfg.page.margins.bottom == "20mm"
    assert cfg.page.margins.left == "30mm"
    assert cfg.font.family == "Times New Roman"
    assert cfg.font.size == "14pt"
    assert cfg.font.line_spacing == 1.5
    assert cfg.paragraph.alignment == "justify"
    assert cfg.paragraph.indent_first_line == "1.25cm"


class TestGost7322017PresetContent:
    def test_gost_7_32_2017_resolved_values(self) -> None:
        cfg = load_config_from_string("preset: gost-7-32-2017\n")

        assert cfg.preset == "gost-7-32-2017"
        _assert_common_body_config(cfg, right_margin="15mm")
        # Inline-код: Courier New на 1pt меньше тела (14pt → 13pt),
        # чтобы моноширинный шрифт не читался крупнее основного текста.
        assert cfg.paragraph.inline_code.font == "Courier New"
        assert cfg.paragraph.inline_code.size == "13pt"
        assert cfg.paragraph.inline_code.italic is False
        assert cfg.paragraph.inline_code.quotes is False
        assert cfg.headings.numbering == "continuous"
        _assert_heading(
            cfg.headings.levels[1],
            size="14pt",
            bold=True,
            italic=False,
            uppercase=True,
            alignment="left",
            space_before="0pt",
            space_after="0pt",
            page_break_before=True,
            indent_first_line="1.25cm",
        )
        _assert_heading(
            cfg.headings.levels[2],
            size="14pt",
            bold=True,
            italic=False,
            uppercase=False,
            alignment="left",
            space_before="12pt",
            space_after="0pt",
            page_break_before=False,
            indent_first_line="1.25cm",
        )
        _assert_heading(
            cfg.headings.levels[3],
            size="14pt",
            bold=True,
            italic=False,
            uppercase=False,
            alignment="left",
            space_before="12pt",
            space_after="0pt",
            page_break_before=False,
            indent_first_line="1.25cm",
        )
        _assert_heading(
            cfg.headings.structural,
            size="14pt",
            bold=True,
            italic=False,
            uppercase=True,
            alignment="center",
            space_before="0pt",
            space_after="0pt",
            page_break_before=True,
            indent_first_line="0cm",
        )
        _assert_caption(
            cfg.captions.image,
            italic=False,
            bold=False,
            alignment="center",
            format="{category} {number} — {text}",
            space_before="4pt",
            space_after="8pt",
            line_spacing=1.0,
        )
        _assert_caption(
            cfg.captions.table,
            italic=False,
            bold=False,
            alignment="left",
            format="{category} {number} — {text}",
            space_before="4pt",
            space_after="2pt",
            line_spacing=1.0,
        )
        _assert_caption(
            cfg.captions.listing,
            italic=False,
            bold=False,
            alignment="left",
            format="{category} {number} — {text}",
            space_before="0pt",
            space_after="0pt",
            line_spacing=1.0,
        )
        assert cfg.captions.continuation_break is False
        assert cfg.listing.font.family == "Consolas"
        assert cfg.listing.font.size == "12pt"
        assert cfg.listing.space_after == "12pt"
        assert cfg.table.space_after == "6pt"
        assert cfg.listing.line_spacing == 1.0
        assert cfg.equation.numbering_alignment == "right"
        assert cfg.equation.parentheses is True


