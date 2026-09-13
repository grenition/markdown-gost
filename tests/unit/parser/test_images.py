from markdown_gost.core import ast
from markdown_gost.core.parser import parse


def _first_image(src: str) -> ast.Image:
    doc = parse(src)
    for block in doc.children:
        for child in getattr(block, "children", []):
            if isinstance(child, ast.Image):
                return child
    raise AssertionError("no image found")


def test_simple_image():
    img = _first_image("![alt](img.png)\n")
    assert img.src == "img.png"
    assert img.alt == "alt"
    assert img.title is None
    assert img.identifier is None
    assert img.width is None and img.height is None


def test_image_with_identifier_and_literal_title():
    img = _first_image('![Большая подпись](img.png "%img literal title"){#img}\n')
    assert img.identifier == "img"
    assert img.alt == "Большая подпись"
    assert img.title == "%img literal title"


def test_image_with_attrs_percent():
    img = _first_image("![](img.png){width=80%}\n")
    assert img.width == ast.Length(value=80.0, unit="%")
    assert img.height is None


def test_image_with_attrs_cm_and_auto():
    img = _first_image("![](img.png){width=10cm height=auto}\n")
    assert img.width == ast.Length(value=10.0, unit="cm")
    assert img.height == ast.Length(value=0.0, unit="auto")


def test_two_images_get_their_own_attrs():
    doc = parse("![](a.png){width=50%}\n\n![](b.png){width=10cm}\n")
    images: list[ast.Image] = []
    for block in doc.children:
        for child in getattr(block, "children", []):
            if isinstance(child, ast.Image):
                images.append(child)
    assert len(images) == 2
    assert images[0].src == "a.png"
    assert images[0].width == ast.Length(value=50.0, unit="%")
    assert images[1].src == "b.png"
    assert images[1].width == ast.Length(value=10.0, unit="cm")
