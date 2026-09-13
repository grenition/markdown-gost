from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_plain_paragraph():
    doc = parse("Просто текст.\n")
    assert len(doc.children) == 1
    p = doc.children[0]
    assert isinstance(p, ast.Paragraph)
    assert isinstance(p.children[0], ast.Text)
    assert p.children[0].text == "Просто текст."


def test_inline_formatting():
    doc = parse("Обычный **жирный** *курсив* `код` [ссылка](https://example.com).\n")
    p = doc.children[0]
    types = [type(c).__name__ for c in p.children]
    assert "Strong" in types
    assert "Emphasis" in types
    assert "InlineCode" in types
    assert "Link" in types


def test_underline_inline():
    doc = parse("Текст [подчёркнутый]{.underline} хвост.\n")
    p = doc.children[0]
    types = [type(c).__name__ for c in p.children]
    assert "Underline" in types
    underline = next(c for c in p.children if isinstance(c, ast.Underline))
    assert isinstance(underline.children[0], ast.Text)
    assert underline.children[0].text == "подчёркнутый"


def test_underline_inside_strong():
    doc = parse("**жир [под]{.underline} жир**\n")
    p = doc.children[0]
    strong = p.children[0]
    assert isinstance(strong, ast.Strong)
    assert any(isinstance(c, ast.Underline) for c in strong.children)


def test_double_plus_around_space_is_not_underline():
    """`++ text ++` не должен матчиться (требуется отсутствие пробела на границах)."""
    doc = parse("a ++ x ++ b\n")
    p = doc.children[0]
    assert not any(isinstance(c, ast.Underline) for c in p.children)


def test_link_attributes():
    doc = parse("[Google](https://google.com)\n")
    link = doc.children[0].children[0]
    assert isinstance(link, ast.Link)
    assert link.url == "https://google.com"
    assert isinstance(link.children[0], ast.Text)
    assert link.children[0].text == "Google"


def test_multiple_paragraphs():
    doc = parse("Первый.\n\nВторой.\n\nТретий.\n")
    paragraphs = [c for c in doc.children if isinstance(c, ast.Paragraph)]
    assert len(paragraphs) == 3
