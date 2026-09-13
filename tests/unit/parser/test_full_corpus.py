"""Корпус-тест: исполняемые примеры из skills/markdown-gost/syntax.md."""

from pathlib import Path

from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def _find_syntax_md() -> Path:
    """Ищем skills/markdown-gost/syntax.md, обходя предков файла теста.

    Простой ``parents[N]`` ломается, когда тест запускается из контейнера, где
    рабочая директория и mount layout отличаются от локальной checkout-копии.
    """

    here = Path(__file__).resolve()
    for ancestor in [here.parent, *here.parents]:
        candidate = ancestor / "skills" / "markdown-gost" / "syntax.md"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "skills/markdown-gost/syntax.md not found in any ancestor of "
        f"{here} — # bind-mount via docker-compose.test.yml). "
        "bind-mount via docker-compose.test.yml)."
    )


SYNTAX_MD = _find_syntax_md()


def _examples(text):
    """Parse every executable Markdown example, not its code-fence wrapper."""
    guide = parse(text)
    return ast.Document(
        children=[
            child
            for node in guide.children
            if isinstance(node, ast.Listing) and node.language == "markdown"
            for child in parse(node.code).children
        ]
    )


def _walk(node):
    yield node
    for attr in ("children", "items", "rows", "cells"):
        for child in getattr(node, attr, []) or []:
            if isinstance(child, ast.Node):
                yield from _walk(child)


def test_syntax_md_parses_into_expected_nodes():
    text = SYNTAX_MD.read_text(encoding="utf-8")
    doc = _examples(text)
    types = {type(n).__name__ for n in _walk(doc)}
    # Каждый из основных синтаксических элементов должен встретиться.
    expected = {
        "Heading",
        "Paragraph",
        "Image",
        "Caption",
        "Table",
        "Listing",
        "Equation",
        "InlineEquation",
        "List",
        "ListItem",
        "TemplateBlock",
        "PageBreak",
        "Mermaid",
    }
    missing = expected - types
    assert not missing, f"missing node types: {missing}"


def test_syntax_md_unnumbered_heading_detected():
    text = SYNTAX_MD.read_text(encoding="utf-8")
    doc = _examples(text)
    headings = [n for n in _walk(doc) if isinstance(n, ast.Heading)]
    unnumbered = [h for h in headings if not h.numbered]
    assert len(unnumbered) >= 2


def test_syntax_md_short_and_long_templates():
    text = SYNTAX_MD.read_text(encoding="utf-8")
    doc = _examples(text)
    tpls = [n for n in _walk(doc) if isinstance(n, ast.TemplateBlock)]
    assert any(t.name == "content" and t.params["depth"] == 3 for t in tpls)
    # Длинная форма обязана быть распознана отдельным узлом, даже если YAML
    # внутри (как в текущем примере) семантически невалидный — параметры
    # тогда останутся пустыми, но узел должен существовать.
    titlepage = [t for t in tpls if t.name == "titlepage-university"]
    assert len(titlepage) == 1
