from __future__ import annotations

from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_appendix_directive_parses_title() -> None:
    doc = parse("# Исходные данные {.appendix}\n\nТекст приложения.\n")

    assert isinstance(doc.children[0], ast.AppendixStart)
    assert doc.children[0].title == "Исходные данные"


def test_appendix_directive_can_omit_title() -> None:
    doc = parse("# {.appendix}\n\nТекст приложения.\n")

    assert isinstance(doc.children[0], ast.AppendixStart)
    assert doc.children[0].title == ""


def test_appendix_directive_is_not_parsed_as_caption() -> None:
    doc = parse("# Исходные данные {.appendix}\n")

    assert isinstance(doc.children[0], ast.AppendixStart)
