from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def test_fenced_code_with_language():
    src = "```python\nprint(1)\n```\n"
    doc = parse(src)
    listing = doc.children[0]
    assert isinstance(listing, ast.Listing)
    assert listing.language == "python"
    assert listing.code == "print(1)\n"


def test_fenced_code_without_language():
    src = "```\nfoo\n```\n"
    doc = parse(src)
    listing = doc.children[0]
    assert isinstance(listing, ast.Listing)
    assert listing.language is None


def test_caption_before_listing():
    src = "```python\ndef f():\n    return 1\n```\n\n: Merge sort\n"
    doc = parse(src)
    types = [type(c).__name__ for c in doc.children]
    assert types == ["Caption", "Listing"]
    assert doc.children[0].target == "listing"
    assert doc.children[0].text == "Merge sort"
    assert doc.children[1].language == "python"
