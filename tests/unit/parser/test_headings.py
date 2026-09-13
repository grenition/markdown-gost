from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def _heading(text: str) -> ast.Heading:
    doc = parse(text)
    headings = [c for c in doc.children if isinstance(c, ast.Heading)]
    assert len(headings) == 1, f"expected exactly one heading, got {doc.children}"
    return headings[0]


def test_basic_h1_is_numbered():
    h = _heading("# Заголовок\n")
    assert h.level == 1
    assert h.numbered is True
    assert _flatten(h.children) == "Заголовок"


def test_levels_h2_h6():
    for level, hashes in enumerate(["##", "###", "####", "#####", "######"], start=2):
        h = _heading(f"{hashes} Текст\n")
        assert h.level == level


def test_unnumbered_with_attribute():
    h = _heading("# СОДЕРЖАНИЕ {.unnumbered}\n")
    assert h.level == 1
    assert h.numbered is False
    assert _flatten(h.children) == "СОДЕРЖАНИЕ"


def test_unnumbered_lower_level():
    h = _heading("### Заголовок без нумерации {.unnumbered}\n")
    assert h.level == 3
    assert h.numbered is False
    assert _flatten(h.children) == "Заголовок без нумерации"


def test_inline_formatting_inside_heading():
    h = _heading("## Hello **bold**\n")
    assert h.numbered is True
    assert any(isinstance(c, ast.Strong) for c in h.children)


def _flatten(children) -> str:
    parts = []
    for c in children:
        if isinstance(c, ast.Text):
            parts.append(c.text)
        elif hasattr(c, "children"):
            parts.append(_flatten(c.children))
    return "".join(parts)
