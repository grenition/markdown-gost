"""Юнит-тесты для :class:`markdown_gost.renderable.image.Image` и Caption."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm, Length, Pt

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.core.ast import nodes as ast
from markdown_gost.render.document_factory import build_document
from markdown_gost.render.layout_tracker import LayoutState
from markdown_gost.render.numberer import Numberer
from markdown_gost.renderable.caption import Caption
from markdown_gost.renderable.factory import RenderableFactory
from markdown_gost.renderable.image import Image
from markdown_gost.renderable.paragraph import Paragraph
from markdown_gost.storage.fs import FilesystemStorage

FIXTURES = Path(__file__).parent / "_fixtures"


@pytest.fixture
def config():
    return load_config_from_string("preset: default\n")


@pytest.fixture
def document(config):
    return build_document(config)


@pytest.fixture
def storage():
    return FilesystemStorage(base_dir=FIXTURES)


@pytest.fixture
def layout(config):
    # Layout с разумным размером колонки. EMU.
    return LayoutState(max_height=Cm(20), max_width=Cm(15))


def _drain(image: Image, layout: LayoutState):
    items = list(image.render(None, layout))
    return items


def _spacing_attrs(paragraph):
    spacing = paragraph._p.find(qn("w:pPr") + "/" + qn("w:spacing"))
    assert spacing is not None
    return spacing


def test_image_renders_centered_paragraph(document, config, storage, layout):
    node = ast.Image(src="sample.png", alt="Подпись")
    image = Image(document, config, node, storage)
    image.set_number(1)
    items = _drain(image, layout)
    assert len(items) >= 1
    pic_info = items[0]
    assert pic_info.docx_element.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER
    # Caption — следом
    assert any("Рисунок" in getattr(it.docx_element, "text", "") for it in items[1:])


def test_image_caption_uses_alt_text(document, config, storage, layout):
    node = ast.Image(src="sample.png", alt="Зоркий сокол")
    image = Image(document, config, node, storage)
    image.set_number(2)
    items = _drain(image, layout)
    caption_text = items[-1].docx_element.text
    assert "Рисунок" in caption_text
    assert "2" in caption_text
    assert "Зоркий сокол" in caption_text


def test_image_caption_without_alt_drops_dash(document, config, storage, layout):
    node = ast.Image(src="sample.png", alt="")
    image = Image(document, config, node, storage)
    image.set_number(3)
    items = _drain(image, layout)
    caption_text = items[-1].docx_element.text
    assert "Рисунок 3" in caption_text
    # «—» должен быть подчищён
    assert not caption_text.rstrip().endswith("—")


def test_image_clamps_width_to_column(document, config, storage, layout):
    # Заявляем 25cm — больше колонки (15cm); должен ужаться до колонки.
    node = ast.Image(
        src="sample.png", alt="x", width=ast.Length(value=25.0, unit="cm")
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    assert image._picture is not None  # type: ignore[attr-defined]
    assert int(image._picture.width) <= int(layout.max_width)  # type: ignore[attr-defined]


def test_image_explicit_cm_width(document, config, storage, layout):
    node = ast.Image(
        src="sample.png", alt="x", width=ast.Length(value=10.0, unit="cm")
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    pic = image._picture  # type: ignore[attr-defined]
    assert pic is not None
    assert pic.width == Cm(10)


def test_image_percent_width_relative_to_column(document, config, storage, layout):
    node = ast.Image(
        src="sample.png", alt="x", width=ast.Length(value=50.0, unit="%")
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    pic = image._picture  # type: ignore[attr-defined]
    assert pic is not None
    # 50% от 15cm = 7.5cm. Допускаем +-1 EMU погрешности округления.
    expected = int(Cm(15) * 0.5)
    assert abs(int(pic.width) - expected) <= 1


def test_image_only_height_keeps_aspect(document, config, storage, layout):
    # sample.png — 200x100 (2:1). При height=2cm width должен быть ~4cm.
    node = ast.Image(
        src="sample.png", alt="x", height=ast.Length(value=2.0, unit="cm")
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    pic = image._picture  # type: ignore[attr-defined]
    assert pic is not None
    assert pic.height == Cm(2)
    # ширина ~ 4 см (2:1 aspect)
    expected_w = Cm(4)
    assert abs(int(pic.width) - int(expected_w)) <= int(Cm(0.1))


def test_image_explicit_both_dims_no_aspect(document, config, storage, layout):
    node = ast.Image(
        src="sample.png",
        alt="x",
        width=ast.Length(value=5.0, unit="cm"),
        height=ast.Length(value=8.0, unit="cm"),
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    pic = image._picture  # type: ignore[attr-defined]
    assert pic.width == Cm(5)
    assert pic.height == Cm(8)


def test_image_height_auto_means_aspect(document, config, storage, layout):
    node = ast.Image(
        src="sample.png",
        alt="x",
        width=ast.Length(value=8.0, unit="cm"),
        height=ast.Length(value=0.0, unit="auto"),
    )
    image = Image(document, config, node, storage)
    image.set_number(1)
    _drain(image, layout)
    pic = image._picture  # type: ignore[attr-defined]
    assert pic.width == Cm(8)
    # 200x100 → 2:1 → 4cm
    assert abs(int(pic.height) - int(Cm(4))) <= int(Cm(0.1))


def test_image_broken_path_renders_placeholder(document, config, storage, layout):
    node = ast.Image(src="does-not-exist.png", alt="x")
    image = Image(document, config, node, storage)
    image.set_number(1)
    items = _drain(image, layout)
    assert image.is_invalid
    # placeholder-параграф + caption
    assert len(items) >= 2
    placeholder_text = items[0].docx_element.text
    assert "Изображение не загружено" in placeholder_text
    assert "image not available" not in placeholder_text
    assert "a:blip" in items[0].docx_element._p.xml
    assert "Рисунок 1 — x" in items[1].docx_element.text


def test_image_placeholder_honors_explicit_dimensions(document, config, storage, layout):
    node = ast.Image(
        src="does-not-exist.png",
        alt="x",
        width=ast.Length(value=5.0, unit="cm"),
        height=ast.Length(value=2.0, unit="cm"),
    )
    image = Image(document, config, node, storage)
    image.set_number(1)

    _drain(image, layout)

    picture = image._picture  # type: ignore[attr-defined]
    assert picture is not None
    assert picture.width == Cm(5)
    assert picture.height == Cm(2)


def test_image_placeholder_default_width_is_bounded_to_content_width(
    document, config, storage, layout
):
    image = Image(document, config, ast.Image(src="does-not-exist.png", alt="x"), storage)
    image.set_number(1)

    _drain(image, layout)

    picture = image._picture  # type: ignore[attr-defined]
    assert picture is not None
    assert picture.width == layout.max_width


def test_image_placeholder_moves_when_only_picture_fits_remaining_page(
    document, config, storage
):
    layout = LayoutState(max_height=Pt(200), max_width=Cm(15))
    layout.add_height(Pt(94))
    remaining = layout.remaining_page_height
    image = Image(
        document,
        config,
        ast.Image(
            src="does-not-exist.png",
            alt="Схема",
            width=ast.Length(value=100.0, unit="pt"),
            height=ast.Length(value=100.0, unit="pt"),
        ),
        storage,
    )
    image.set_number(1)

    first = next(image.render(None, layout))

    assert int(first.height) == int(remaining) + int(Pt(100)) + int(Pt(12))


def test_image_factory_dispatches_block(document, config, storage):
    f = RenderableFactory(document, config, Numberer(), storage=storage)
    doc_ast = ast.Document(
        children=[
            ast.Paragraph(children=[ast.Image(src="sample.png", alt="ОдинокаяКартинка")])
        ]
    )
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Image)


def test_image_factory_inline_when_mixed_with_text(document, config, storage):
    f = RenderableFactory(document, config, Numberer(), storage=storage)
    doc_ast = ast.Document(
        children=[
            ast.Paragraph(
                children=[
                    ast.Text(text="перед "),
                    ast.Image(src="sample.png", alt="x"),
                    ast.Text(text=" после"),
                ]
            )
        ]
    )
    rendered = f.create_all(doc_ast)
    assert len(rendered) == 1
    assert isinstance(rendered[0], Paragraph)
    assert not isinstance(rendered[0], Image)


def test_caption_format_image(document, config):
    cap = Caption(document, config, category="image", number=5, text="Подпись")
    text = cap.docx_paragraph.text
    assert "Рисунок 5" in text
    assert "Подпись" in text


def test_caption_accepts_appendix_display_number(document, config):
    cap = Caption(document, config, category="image", number="А.1", text="Схема")
    text = cap.docx_paragraph.text
    assert "Рисунок А.1" in text
    assert "Схема" in text


def test_caption_alignment_for_image_is_center(document, config):
    cap = Caption(document, config, category="image", number=1, text="x")
    assert cap.docx_paragraph.alignment == WD_PARAGRAPH_ALIGNMENT.CENTER


def test_caption_strips_dash_for_empty_text(document, config):
    cap = Caption(document, config, category="image", number=7, text=None)
    text = cap.docx_paragraph.text
    assert "Рисунок 7" in text
    assert not text.rstrip().endswith("—")


def test_caption_honors_config_overrides():
    """Overrides из config.captions.image должны применяться к подписи:
    italic-флаг попадает в run, alignment — в параграф, format — в текст.
    """

    config = load_config_from_string(
        """
preset: default
overrides:
  captions:
    image:
      italic: true
      bold: false
      alignment: left
      format: "Рис. {number}. {text}"
"""
    )
    document = build_document(config)
    cap = Caption(document, config, category="image", number=4, text="Карта местности")

    assert cap.docx_paragraph.alignment == WD_PARAGRAPH_ALIGNMENT.LEFT
    assert cap.docx_paragraph.text == "Рис. 4. Карта местности"

    runs = [r for r in cap.docx_paragraph.runs if r.text]
    assert runs, "ожидался хотя бы один run с текстом"
    assert all(r.italic for r in runs), "italic должен примениться ко всем runs"
    # bold явно false — runs не должны быть жирными
    assert not any(r.bold for r in runs)


def test_caption_applies_space_before_from_spec():
    """T013b: ``CaptionStyle.space_before`` транслируется в paragraph_format.

    Если в config'е переопределён ``captions.image.space_before: 6pt`` — это
    значение должно попасть в ``paragraph_format.space_before`` подписи.
    """

    config = load_config_from_string(
        "preset: default\noverrides:\n  captions:\n    image:\n      space_before: 6pt\n"
    )
    document = build_document(config)
    cap = Caption(document, config, category="image", number=1, text="x")
    pf = cap.docx_paragraph.paragraph_format
    # 6pt в EMU. Pt(6) = 76200 EMU.
    assert int(pf.space_before) == 76200


def test_caption_applies_space_after_from_spec():
    """T013b: ``CaptionStyle.space_after`` транслируется в paragraph_format."""

    config = load_config_from_string(
        "preset: default\noverrides:\n  captions:\n    image:\n      space_after: 12pt\n"
    )
    document = build_document(config)
    cap = Caption(document, config, category="image", number=1, text="x")
    pf = cap.docx_paragraph.paragraph_format
    assert int(pf.space_after) == 152400  # 12pt = 152400 EMU


def test_caption_zero_spacing_when_overridden():
    """Override ``space_before/after`` = 0pt → 0 EMU."""

    config = load_config_from_string(
        "preset: default\n"
        "overrides:\n"
        "  captions:\n"
        "    image:\n"
        "      space_before: 0pt\n"
        "      space_after: 0pt\n"
    )
    document = build_document(config)
    cap = Caption(document, config, category="image", number=1, text="x")
    pf = cap.docx_paragraph.paragraph_format
    assert int(pf.space_before) == 0
    assert int(pf.space_after) == 0


def test_caption_does_not_set_line_spacing_when_unset(document, config):
    """Legacy default: caption line spacing inherits from the body/Normal style."""

    cap = Caption(document, config, category="image", number=1, text="x")
    pf = cap.docx_paragraph.paragraph_format
    spacing = _spacing_attrs(cap.docx_paragraph)
    assert pf.line_spacing is None
    assert spacing.get(qn("w:line")) is None
    assert spacing.get(qn("w:lineRule")) is None


def test_caption_applies_line_spacing_from_spec():
    config = load_config_from_string(
        "preset: default\noverrides:\n  captions:\n    image:\n      line_spacing: 1.0\n"
    )
    document = build_document(config)
    cap = Caption(document, config, category="image", number=1, text="x")
    pf = cap.docx_paragraph.paragraph_format
    spacing = _spacing_attrs(cap.docx_paragraph)
    assert pf.line_spacing == 1.0
    assert spacing.get(qn("w:line")) == "240"
    assert spacing.get(qn("w:lineRule")) == "auto"


def test_mirea_image_caption_is_italic_and_single_spaced(storage, layout):
    config = load_config_from_string("preset: mirea-practice\n")
    doc = build_document(config)
    node = ast.Image(src="sample.png", alt="Длинная подпись")
    image = Image(doc, config, node, storage)
    image.set_number(1)
    items = list(image.render(None, layout))
    cap_para = items[-1].docx_element
    spacing = _spacing_attrs(cap_para)
    assert cap_para.paragraph_format.line_spacing == 1.0
    assert spacing.get(qn("w:line")) == "240"
    assert spacing.get(qn("w:lineRule")) == "auto"
    runs = [r for r in cap_para.runs if r.text]
    assert runs
    assert all(r.italic for r in runs)


def test_image_caption_inherits_image_spacing(document, storage, layout):
    """T013b: ``captions.image.space_after`` накладывается на параграф подписи картинки."""

    config = load_config_from_string(
        "preset: default\noverrides:\n  captions:\n    image:\n      space_after: 6pt\n"
    )
    doc = build_document(config)
    node = ast.Image(src="sample.png", alt="x")
    image = Image(doc, config, node, storage)
    image.set_number(1)
    items = list(image.render(None, layout))
    # Последний item — caption-параграф.
    cap_para = items[-1].docx_element
    assert int(cap_para.paragraph_format.space_after) == 76200


def test_inline_image_in_paragraph_renders_picture(document, config, storage, layout):
    """Inline картинка в параграфе вставляется в run."""

    node = ast.Paragraph(
        children=[
            ast.Text(text="до "),
            ast.Image(src="sample.png", alt="ignored"),
            ast.Text(text=" после"),
        ]
    )
    p = Paragraph(document, config, storage=storage)
    p.add_inline_nodes(node.children)
    # Один из ранов содержит embedded picture (drawing element).
    runs_xml = [r._element.xml for r in p.docx_paragraph.runs]
    has_picture = any("graphicData" in xml or "drawing" in xml for xml in runs_xml)
    assert has_picture, "expected inline picture in paragraph runs"


def test_inline_image_broken_path_emits_placeholder_text(document, config, storage):
    p = Paragraph(document, config, storage=storage)
    p.add_inline_nodes(
        [
            ast.Text(text="до "),
            ast.Image(src="missing.png", alt="x"),
            ast.Text(text=" после"),
        ]
    )
    text = p.docx_paragraph.text
    assert "[Изображение не загружено: x]" in text
    assert "image not available" not in text
    assert "a:blip" in p.docx_paragraph._p.xml


def test_inline_image_broken_path_without_alt_uses_generic_placeholder(
    document, config, storage
):
    p = Paragraph(document, config, storage=storage)
    p.add_inline_nodes([ast.Image(src="missing.png", alt="")])

    assert "[Изображение не загружено]" in p.docx_paragraph.text


_ = Length  # keep import alive for static checkers
