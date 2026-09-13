from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_reference_inline():
    doc = parse("См. [](#products) далее.\n")
    p = doc.children[0]
    refs = [c for c in p.children if isinstance(c, ast.Reference)]
    assert len(refs) == 1
    assert refs[0].type == ""
    assert refs[0].name == "products"


def test_multiple_references():
    doc = parse("Сравните [](#cat) и [](#dog).\n")
    p = doc.children[0]
    refs = [c for c in p.children if isinstance(c, ast.Reference)]
    assert [r.name for r in refs] == ["cat", "dog"]


def test_reference_does_not_match_email():
    # У ссылок нет двоеточия после имени, а email содержит @ перед именем без `:`.
    doc = parse("Связаться: foo@example.com.\n")
    p = doc.children[0]
    refs = [c for c in p.children if isinstance(c, ast.Reference)]
    assert refs == []
