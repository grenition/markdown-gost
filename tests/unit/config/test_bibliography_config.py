from __future__ import annotations

from markdown_gost.config.loader import load_config_from_string


def test_bibliography_config_defaults() -> None:
    cfg = load_config_from_string("preset: default\n")

    assert cfg.bibliography.citation_format == "[{n}]"
    assert cfg.bibliography.order == "citation"
    assert cfg.bibliography.style == "minimal-gost"
    assert cfg.bibliography.entry_number_format == "{n}."


def test_bibliography_config_override() -> None:
    cfg = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  bibliography:\n"
        "    citation_format: \"({n})\"\n"
        "    order: input\n"
        "    style: minimal-gost\n"
        "    entry_number_format: \"[{n}]\"\n"
    )

    assert cfg.bibliography.citation_format == "({n})"
    assert cfg.bibliography.order == "input"
    assert cfg.bibliography.style == "minimal-gost"
    assert cfg.bibliography.entry_number_format == "[{n}]"
