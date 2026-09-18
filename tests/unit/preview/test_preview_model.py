from __future__ import annotations

import json
import logging
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import BaseModel

from markdown_gost.config.loader import load_config_from_string
from markdown_gost.config.schema import Config
from markdown_gost.core.parser import parse
from markdown_gost.preview import build_preview_model, render_preview_html
from markdown_gost.preview.model import PreviewInline
from markdown_gost.render.render_index import RenderIndex
from markdown_gost.storage import FilesystemStorage
from markdown_gost.templates import PreviewTemplateContext, register, unregister


class RecordingStorage:
    def __init__(self) -> None:
        self.fetches: list[str] = []
        self.exists_checks: list[str] = []
        self.stats: list[str] = []
        self.puts: list[tuple[str, bytes]] = []

    def fetch(self, src: str) -> bytes:
        self.fetches.append(src)
        return b"raw-image-bytes"

    def exists(self, src: str) -> bool:
        self.exists_checks.append(src)
        return True

    def stat(self, src: str) -> object:
        self.stats.append(src)
        raise AssertionError("preview model must not stat image bytes")

    def put(self, key: str, data: bytes) -> None:
        self.puts.append((key, data))


def _config(overrides: str = "") -> Config:
    return load_config_from_string(f"preset: gost-7-32-2017\n{overrides}")


def test_page_geometry_uses_config_physical_units() -> None:
    cfg = _config(
        "overrides:\n"
        "  page:\n"
        "    size: A3\n"
        "    orientation: landscape\n"
        "    margins:\n"
        "      top: 10mm\n"
        "      right: 15mm\n"
        "      bottom: 20mm\n"
        "      left: 30mm\n"
    )

    model = build_preview_model("Text\n", cfg, RecordingStorage())

    assert model.geometry.page_size == "A3"
    assert model.geometry.orientation == "landscape"
    assert model.geometry.width.value == 420.0
    assert model.geometry.height.value == 297.0
    assert model.geometry.width.unit == "mm"
    assert model.geometry.margins.left.value == 30.0
    assert model.geometry.margins.right.value == 15.0
    assert model.geometry.content_width.value == 375.0
    assert model.geometry.content_height.value == 267.0


def test_hard_page_break_splits_pages_without_pdf_pipeline() -> None:
    model = build_preview_model(
        "Before\n\n::: {.page-break}\n:::\n\nAfter\n", _config(), RecordingStorage()
    )

    assert model.total_pages == 2
    assert [page.number for page in model.pages] == [1, 2]
    assert [block.kind for block in model.pages[0].blocks] == ["paragraph", "page_break"]
    assert [block.kind for block in model.pages[1].blocks] == ["paragraph"]
    assert model.pages[0].blocks[0].text == "Before"
    assert model.pages[1].blocks[0].text == "After"


def test_titlepage_template_is_visible_and_forces_following_content_to_next_page() -> None:
    model = build_preview_model(
        '::: {.template name="titlepage-university"}\n'
        "title: Preview title\n"
        "city: МОСКВА\n"
        "year: 2026 г.\n"
        ":::\n\n"
        "Following content\n",
        _config(),
        RecordingStorage(),
    )

    assert model.total_pages == 2
    title_page = model.pages[0].blocks[0]
    assert title_page.kind == "title_page"
    assert title_page.layout is not None
    assert {item["text"] for item in title_page.layout["work"]} >= {"Preview title"}
    assert [block.text for block in model.pages[1].blocks] == ["Following content"]


def test_titlepage_template_isolated_between_normal_content() -> None:
    model = build_preview_model(
        "Before\n\n"
        '::: {.template name="titlepage-university"}\n'
        "title: Preview title\n"
        "city: МОСКВА\n"
        "year: 2026 г.\n"
        ":::\n\n"
        "After\n",
        _config(),
        RecordingStorage(),
    )

    assert model.total_pages == 3
    assert [block.text for block in model.pages[0].blocks] == ["Before"]
    assert [block.kind for block in model.pages[1].blocks] == [
        "title_page",
        "page_break",
    ]
    assert [block.text for block in model.pages[2].blocks] == ["After"]


def test_titlepage_template_uses_semantic_layout_with_signatures_and_footer() -> None:
    model = build_preview_model(
        '::: {.template name="titlepage-university"}\n'
        "title: Preview title\n"
        "authors:\n"
        "  - label: Student\n"
        "    names: [Author]\n"
        "reviewers:\n"
        "  - label: Reviewer\n"
        "    names: [Teacher]\n"
        "city: МОСКВА\n"
        "year: 2026 г.\n"
        ":::\n",
        _config(),
        RecordingStorage(),
    )

    title_page = model.pages[0].blocks[0]

    assert title_page.kind == "title_page"
    assert title_page.layout is not None
    assert title_page.layout["footer"] == "МОСКВА 2026 г."
    assert title_page.layout["signature_sections"][0]["rows"] == [
        {"label": "Student", "name": "Author"}
    ]


def test_content_template_uses_one_semantic_toc_entry_per_heading() -> None:
    model = build_preview_model(
        '::: {.template name="content"}\n:::\n\n# Intro\n\n## Details\n',
        _config(),
        RecordingStorage(),
    )

    toc = next(block for block in model.pages[0].blocks if block.kind == "toc")

    assert toc.layout is not None
    assert toc.layout["dot_leader"] is True
    assert toc.layout["entries"] == [
        {
            "anchor": model.anchors[0].anchor,
            "level": 1,
            "number": "1",
            "numbered": True,
            "page": model.anchors[0].page,
            "text": "Intro",
        },
        {
            "anchor": model.anchors[1].anchor,
            "level": 2,
            "number": "1.1",
            "numbered": True,
            "page": model.anchors[1].page,
            "text": "Details",
        },
    ]
    assert json.dumps(model.to_dict(), allow_nan=False)
    assert model.to_json()


def test_content_template_paginates_long_deferred_toc_and_shifts_heading_pages() -> None:
    headings = [
        (f"Heading {number:03d} — " + "long eligible heading text " * 4).strip()
        for number in range(1, 81)
    ]
    markdown = '::: {.template name="content"}\ndepth: 6\n:::\n\n' + "\n\n".join(
        f"# {text}" for text in headings
    )

    model = build_preview_model(markdown, _config(), RecordingStorage())

    toc_blocks = [block for page in model.pages for block in page.blocks if block.kind == "toc"]
    toc_entries = [entry for block in toc_blocks for entry in (block.layout or {})["entries"]]
    heading_blocks = [
        block
        for page in model.pages
        for block in page.blocks
        if block.kind == "heading" and block.anchor is not None
    ]

    assert len(toc_blocks) > 1
    assert all(block.layout is not None for block in toc_blocks)
    assert all(len(block.layout["entries"]) < len(headings) for block in toc_blocks)
    assert [entry["text"] for entry in toc_entries] == headings
    assert [entry["anchor"] for entry in toc_entries] == [anchor.anchor for anchor in model.anchors]
    assert [block.page for block in heading_blocks] == [anchor.page for anchor in model.anchors]
    assert [entry["page"] for entry in toc_entries] == [anchor.page for anchor in model.anchors]
    assert heading_blocks[0].page == toc_blocks[-1].page + 1
    assert model.total_pages == len(model.pages) == model.pages[-1].number


def test_content_template_moves_first_toc_row_when_title_leaves_no_room() -> None:
    cfg = _config("overrides:\n  page:\n    margins:\n      top: 120mm\n      bottom: 120mm\n")
    heading = "Included heading " * 30

    model = build_preview_model(
        f'::: {{.template name="content"}}\ndepth: 6\n:::\n\n# {heading}\n',
        cfg,
        RecordingStorage(),
    )

    toc_blocks = [block for page in model.pages for block in page.blocks if block.kind == "toc"]
    assert len(toc_blocks) == 2
    assert (toc_blocks[0].layout or {})["entries"] == []
    assert [entry["text"] for entry in (toc_blocks[1].layout or {})["entries"]] == [heading.strip()]


def test_content_template_structural_title_starts_on_fresh_page_after_content() -> None:
    model = build_preview_model(
        "Before content\n\n"
        '::: {.template name="content"}\n'
        ":::\n\n::: {.page-break}\n:::\n\n"
        "# Included\n\n"
        "## Included detail\n",
        _config(),
        RecordingStorage(),
    )

    assert [block.text for block in model.pages[0].blocks] == ["Before content"]
    assert [block.kind for block in model.pages[1].blocks] == ["heading", "toc", "page_break"]
    assert model.pages[1].blocks[0].text == "СОДЕРЖАНИЕ"
    assert [anchor.page for anchor in model.anchors] == [4, 4]
    toc = model.pages[1].blocks[1]
    assert toc.layout is not None
    assert [entry["page"] for entry in toc.layout["entries"]] == [4, 4]
    assert [entry["anchor"] for entry in toc.layout["entries"]] == [
        anchor.anchor for anchor in model.anchors
    ]


def test_preview_template_dispatches_registered_extension_without_name_branch() -> None:
    class Params(BaseModel):
        text: str

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("paragraph", f"Extension: {params['text']}")

    register("preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="preview-extension"}\ntext: registered\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("preview-extension")

    assert [block.text for block in model.pages[0].blocks] == ["Extension: registered"]


def test_preview_template_context_allows_legacy_direct_construction() -> None:
    context = PreviewTemplateContext(
        config=_config(),
        document_ast=parse(""),
        index=RenderIndex(),
        _add_block=lambda *args, **kwargs: None,
        _add_page_break=lambda: None,
        _current_page=lambda: 1,
        _defer=lambda callback: None,
    )

    assert context.template_name == ""


def test_preview_template_extension_inlines_are_copied_materialized_and_serialized() -> None:
    class Params(BaseModel):
        pass

    style = {"font_family": "Arial", "font_size": "12pt", "opacity": 0.75}
    inlines = [
        {"kind": "text", "text": "Text", "bold": True},
        {"kind": "link", "text": "Link", "href": "https://example.test"},
        {
            "kind": "image",
            "src": "/api/preview/assets/example.png",
            "asset_path": "example.png",
            "alt": "Example",
            "width": {"value": 320, "unit": "px"},
            "height": {"value": 180.0, "unit": "px"},
        },
    ]

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("paragraph", "TextLink", style=style, inlines=inlines)
        style["font_family"] = "Mutated"
        inlines[0]["text"] = "Mutated"
        inlines[2]["width"]["value"] = 1

    register("extension-inline-preview", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="extension-inline-preview"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("extension-inline-preview")

    block = model.pages[0].blocks[0]

    assert block.style == {"font_family": "Arial", "font_size": "12pt", "opacity": 0.75}
    assert all(isinstance(inline, PreviewInline) for inline in block.inlines)
    assert block.to_dict()["inlines"] == [
        {"kind": "text", "text": "Text", "bold": True},
        {"kind": "link", "text": "Link", "href": "https://example.test"},
        {
            "kind": "image",
            "src": "/api/preview/assets/example.png",
            "asset_path": "example.png",
            "alt": "Example",
            "width": {"value": 320.0, "unit": "px"},
            "height": {"value": 180.0, "unit": "px"},
        },
    ]
    assert model.to_json()
    rendered = render_preview_html(model)
    assert "Text" in rendered
    assert 'href="https://example.test"' in rendered
    assert 'src="/api/preview/assets/example.png"' in rendered


@pytest.mark.parametrize(
    ("style", "secret"),
    [
        ({"ratio": math.nan}, "style-nan-secret"),
        ({"ratio": math.inf}, "style-infinity-secret"),
        ({"nested": {"value": "not-a-primitive"}}, "style-nested-secret"),
        ({1: "non-string-key"}, "style-key-secret"),
    ],
    ids=["nan", "infinity", "nested", "non-string-key"],
)
def test_preview_template_invalid_style_becomes_generic_diagnostic(
    style: dict[Any, Any], secret: str
) -> None:
    class Params(BaseModel):
        pass

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("extension", "", style=style, block_id=secret)

    register("invalid-style-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="invalid-style-preview-extension"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("invalid-style-preview-extension")

    diagnostic = model.pages[0].blocks[0]

    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == (
        "[template 'invalid-style-preview-extension' error: preview rendering failed]"
    )
    assert secret not in model.to_json()
    assert model.to_json()


@pytest.mark.parametrize(
    ("inlines", "secret"),
    [
        ([{"kind": "text", "unknown": "value"}], "inline-unknown-secret"),
        ([{"kind": "text", "text": object()}], "inline-object-secret"),
        ([{"kind": "text", "text": 1}], "inline-wrong-type-secret"),
        ([{"kind": "image", "width": {"value": math.nan, "unit": "px"}}], "inline-nan-secret"),
        ([{"kind": "image", "height": {"value": 1, "unit": object()}}], "inline-dimension-secret"),
        ([{"kind": "text", "text": "valid"}, object()], "inline-item-secret"),
    ],
    ids=["unknown-key", "object", "wrong-type", "nonfinite", "bad-dimension", "non-dict"],
)
def test_preview_template_malformed_inlines_become_generic_diagnostic(
    inlines: list[Any], secret: str
) -> None:
    class Params(BaseModel):
        pass

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("extension", "", inlines=inlines, block_id=secret)

    register("invalid-inline-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="invalid-inline-preview-extension"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("invalid-inline-preview-extension")

    diagnostic = model.pages[0].blocks[0]

    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == (
        "[template 'invalid-inline-preview-extension' error: preview rendering failed]"
    )
    assert secret not in model.to_json()
    assert model.to_json()


def test_preview_document_json_rejects_nonfinite_values() -> None:
    model = build_preview_model("Body\n", _config(), RecordingStorage())
    block = replace(model.pages[0].blocks[0], style={"ratio": math.nan})
    invalid = replace(model, pages=[replace(model.pages[0], blocks=[block])])

    with pytest.raises(ValueError):
        invalid.to_json()


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("kind", object()),
        ("text", object()),
        ("block_id", object()),
        ("level", math.nan),
        ("numbered", "yes"),
        ("number", object()),
        ("anchor", object()),
    ],
)
def test_preview_template_invalid_scalar_metadata_becomes_generic_diagnostic(
    field_name: str,
    invalid_value: object,
) -> None:
    class Params(BaseModel):
        pass

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        values: dict[str, Any] = {"kind": "extension", "text": ""}
        values[field_name] = invalid_value
        kind = values.pop("kind")
        text = values.pop("text")
        context.add_block(kind, text, **values)

    register("invalid-scalar-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="invalid-scalar-preview-extension"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("invalid-scalar-preview-extension")

    diagnostic = model.pages[0].blocks[0]
    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == (
        "[template 'invalid-scalar-preview-extension' error: preview rendering failed]"
    )
    assert model.to_json()


def test_preview_template_render_failure_is_logged_without_leaking_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Params(BaseModel):
        pass

    secret = "/srv/private/template-render-secret"

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        raise RuntimeError(secret)

    register("failing-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        with caplog.at_level(logging.ERROR, logger="markdown_gost.templates"):
            model = build_preview_model(
                '::: {.template name="failing-preview-extension"}\n:::\n',
                _config(),
                RecordingStorage(),
            )
    finally:
        unregister("failing-preview-extension")

    diagnostic = model.pages[0].blocks[0]
    rendered = render_preview_html(model)

    assert diagnostic.kind == "template_diagnostic"
    assert "preview rendering failed" in diagnostic.text
    assert secret not in diagnostic.text
    assert secret not in rendered
    assert any(record.exc_info is not None for record in caplog.records)


def test_preview_template_import_failure_is_logged_without_leaking_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Params(BaseModel):
        pass

    secret_module = "md2gost_private_template_import_secret"

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    register(
        "unimportable-preview-extension",
        render_unused,
        Params,
        preview_fn=f"{secret_module}:render_preview",
    )
    try:
        with caplog.at_level(logging.ERROR, logger="markdown_gost.templates"):
            model = build_preview_model(
                '::: {.template name="unimportable-preview-extension"}\n:::\n',
                _config(),
                RecordingStorage(),
            )
    finally:
        unregister("unimportable-preview-extension")

    diagnostic = model.pages[0].blocks[0]
    rendered = render_preview_html(model)

    assert diagnostic.kind == "template_diagnostic"
    assert "preview renderer unavailable" in diagnostic.text
    assert secret_module not in diagnostic.text
    assert secret_module not in rendered
    assert any(record.exc_info is not None for record in caplog.records)


def test_preview_template_deferred_failure_becomes_visible_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Params(BaseModel):
        pass

    secret = "/srv/private/deferred-template-secret"

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("paragraph", "Extension content")

        def deferred() -> None:
            raise RuntimeError(secret)

        context.defer(deferred)

    register("deferred-failing-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        with caplog.at_level(logging.ERROR, logger="markdown_gost.preview.builder"):
            model = build_preview_model(
                '::: {.template name="deferred-failing-preview-extension"}\n:::\n\n'
                "Following content\n",
                _config(),
                RecordingStorage(),
            )
    finally:
        unregister("deferred-failing-preview-extension")

    diagnostics = [
        block
        for page in model.pages
        for block in page.blocks
        if block.kind == "template_diagnostic"
    ]

    assert len(diagnostics) == 1
    assert "deferred preview rendering failed" in diagnostics[0].text
    assert "deferred-failing-preview-extension" in diagnostics[0].text
    assert secret not in diagnostics[0].text
    assert diagnostics[0].page in [page.number for page in model.pages]
    assert any(record.exc_info is not None for record in caplog.records)


def test_preview_template_layout_is_recursively_copied_as_json_safe_data() -> None:
    class Params(BaseModel):
        pass

    layout = {
        "title": "Extension layout",
        "items": [{"count": 1, "enabled": True, "ratio": 1.25, "empty": None}],
    }

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("extension_layout", "", layout=layout)
        layout["items"][0]["count"] = 2

    register("json-layout-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="json-layout-preview-extension"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("json-layout-preview-extension")

    block = model.pages[0].blocks[0]
    expected = {
        "title": "Extension layout",
        "items": [{"count": 1, "enabled": True, "ratio": 1.25, "empty": None}],
    }

    assert block.layout == expected
    assert block.to_dict()["layout"] == expected
    assert '"layout":{"items":[{"count":1' in model.to_json()


@pytest.mark.parametrize(
    "invalid_layout",
    [
        {"nested": object()},
        {"ratio": math.nan},
        {"ratio": math.inf},
        {"ratio": -math.inf},
        {1: "non-string key"},
    ],
    ids=["object", "nan", "positive-infinity", "negative-infinity", "non-string-key"],
)
def test_preview_template_invalid_layout_becomes_generic_diagnostic(
    invalid_layout: dict[Any, Any],
) -> None:
    class Params(BaseModel):
        pass

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        context.add_block("extension_layout", "", layout=invalid_layout)

    register("invalid-json-layout-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        model = build_preview_model(
            '::: {.template name="invalid-json-layout-preview-extension"}\n:::\n',
            _config(),
            RecordingStorage(),
        )
    finally:
        unregister("invalid-json-layout-preview-extension")

    diagnostic = model.pages[0].blocks[0]

    assert diagnostic.kind == "template_diagnostic"
    assert "preview rendering failed" in diagnostic.text
    assert "object" not in diagnostic.text
    assert "inf" not in diagnostic.text.lower()
    assert "nan" not in diagnostic.text.lower()
    assert model.to_json()


@pytest.mark.parametrize(
    ("invalid_value", "secret"),
    [
        (math.nan, "deferred-layout-nan-secret"),
        (object(), "deferred-layout-object-secret"),
    ],
    ids=["nan", "object"],
)
def test_preview_template_revalidates_layout_mutated_by_deferred_callback(
    caplog: pytest.LogCaptureFixture,
    invalid_value: Any,
    secret: str,
) -> None:
    class Params(BaseModel):
        pass

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        layout = context.add_block(
            "extension_layout",
            "",
            block_id=secret,
            layout={"entries": []},
        )
        assert layout is not None

        def deferred() -> None:
            layout["entries"].append(invalid_value)

        context.defer(deferred)

    register("deferred-invalid-layout-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        with caplog.at_level(logging.ERROR, logger="markdown_gost.preview.builder"):
            model = build_preview_model(
                "Before\n\n"
                '::: {.template name="deferred-invalid-layout-preview-extension"}\n'
                ":::\n\n::: {.page-break}\n:::\n\n"
                "After\n",
                _config(),
                RecordingStorage(),
            )
    finally:
        unregister("deferred-invalid-layout-preview-extension")

    diagnostic = model.pages[0].blocks[1]

    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == "[template error: preview rendering failed]"
    assert diagnostic.page == 1
    assert [block.kind for block in model.pages[0].blocks] == [
        "paragraph",
        "template_diagnostic",
        "page_break",
    ]
    assert secret not in diagnostic.text
    assert secret not in model.to_json()
    assert json.dumps(model.to_dict(), allow_nan=False)
    assert any(record.exc_info is not None for record in caplog.records)


def test_preview_template_revalidates_cycle_added_by_deferred_callback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Params(BaseModel):
        pass

    secret = "deferred-layout-cycle-secret"

    def render_unused(params: dict[str, Any], parent: Any) -> Any:
        raise AssertionError("DOCX template renderer must not be called by preview")

    def preview(params: dict[str, Any], context: Any) -> None:
        layout = context.add_block(
            "extension_layout",
            "",
            block_id=secret,
            layout={"entries": []},
        )
        assert layout is not None

        def deferred() -> None:
            layout["cycle"] = layout

        context.defer(deferred)

    register("deferred-cycle-layout-preview-extension", render_unused, Params, preview_fn=preview)
    try:
        with caplog.at_level(logging.ERROR, logger="markdown_gost.preview.builder"):
            model = build_preview_model(
                "Before\n\n"
                '::: {.template name="deferred-cycle-layout-preview-extension"}\n'
                ":::\n\n::: {.page-break}\n:::\n\n"
                "After\n",
                _config(),
                RecordingStorage(),
            )
    finally:
        unregister("deferred-cycle-layout-preview-extension")

    diagnostic = model.pages[0].blocks[1]

    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == "[template error: preview rendering failed]"
    assert [block.kind for block in model.pages[0].blocks] == [
        "paragraph",
        "template_diagnostic",
        "page_break",
    ]
    assert secret not in diagnostic.text
    assert secret not in model.to_json()
    assert json.dumps(model.to_dict(), allow_nan=False)
    assert any(record.exc_info is not None for record in caplog.records)


def test_unknown_template_produces_visible_preview_diagnostic() -> None:
    model = build_preview_model(
        '::: {.template name="missing-template"}\n:::\n\nAfter\n',
        _config(),
        RecordingStorage(),
    )

    diagnostic, following = model.pages[0].blocks

    assert diagnostic.kind == "template_diagnostic"
    assert diagnostic.text == "[template 'missing-template' error: template not registered]"
    assert following.text == "After"


def test_heading_blocks_have_render_index_compatible_anchors() -> None:
    model = build_preview_model("# Intro\n\n## Details\n", _config(), RecordingStorage())

    headings = [block for page in model.pages for block in page.blocks if block.kind == "heading"]
    expected = RenderIndex()
    h1 = expected.add_heading(
        level=1,
        text="Intro",
        numbered=True,
        number="1",
        page=1,
    )
    h2 = expected.add_heading(
        level=2,
        text="Details",
        numbered=True,
        number="1.1",
        page=1,
    )

    assert [block.anchor for block in headings] == [h1.anchor, h2.anchor]
    assert [block.number for block in headings] == ["1", "1.1"]
    assert [anchor.anchor for anchor in model.anchors] == [h1.anchor, h2.anchor]
    assert [anchor.block_id for anchor in model.anchors] == [h1.anchor, h2.anchor]


def test_json_serialization_is_stable() -> None:
    cfg = _config()
    first = build_preview_model("# Intro\n\nBody\n", cfg, RecordingStorage())
    second = build_preview_model("# Intro\n\nBody\n", cfg, RecordingStorage())

    assert first.to_json() == second.to_json()
    assert first.to_dict() == second.to_dict()


def test_default_storage_is_optional_for_text_only_preview() -> None:
    model = build_preview_model("Body\n", _config())

    assert model.total_pages == 1
    assert model.pages[0].blocks[0].text == "Body"


def test_inline_images_are_asset_references_without_bytes_or_base64() -> None:
    storage = RecordingStorage()

    model = build_preview_model(
        'Logo ![MIREA](assets/logo.png "Logo") inside text.\n',
        _config(),
        storage,
    )

    assert storage.fetches == []
    assert storage.exists_checks == []
    assert storage.stats == []
    payload = model.to_dict()
    paragraph = payload["pages"][0]["blocks"][0]
    image_inline = paragraph["inlines"][1]
    assert image_inline == {
        "kind": "image",
        "src": "/api/preview/assets/assets%2Flogo.png",
        "asset_path": "assets/logo.png",
        "alt": "MIREA",
        "title": "Logo",
        "aspect_ratio": "16 / 9",
    }
    as_json = model.to_json()
    assert "/api/preview/assets/assets%2Flogo.png" in as_json
    assert "raw-image-bytes" not in as_json
    assert "base64" not in as_json.lower()


def test_many_image_html_preview_does_not_query_storage() -> None:
    storage = RecordingStorage()
    markdown = " ".join(f"![Схема {index}](images/schema-{index}.png)" for index in range(20))

    rendered = render_preview_html(build_preview_model(markdown, _config(), storage))

    assert storage.exists_checks == []
    assert storage.stats == []
    assert storage.fetches == []
    assert rendered.count('loading="lazy"') == 20
    assert rendered.count('decoding="async"') == 20


def test_repeated_image_references_do_not_query_or_serialize_availability() -> None:
    storage = RecordingStorage()

    model = build_preview_model(
        "Before ![Inline](asset) after.\n\n![Block](asset)\n",
        _config(),
        storage,
    )

    inlines = [
        inline
        for page in model.pages
        for block in page.blocks
        for inline in block.inlines
        if inline.kind == "image"
    ]

    assert storage.exists_checks == []
    assert storage.stats == []
    assert storage.fetches == []
    assert [inline.src for inline in inlines] == [
        "/api/preview/assets/asset",
        "/api/preview/assets/asset",
    ]
    assert all("available" not in inline.to_dict() for inline in inlines)


def test_undecodable_filesystem_image_keeps_lazy_asset_reference(tmp_path: Path) -> None:
    (tmp_path / "broken-image").write_text("not an image", encoding="utf-8")

    model = build_preview_model(
        "![Broken](broken-image)\n",
        _config(),
        FilesystemStorage(base_dir=tmp_path),
    )

    image = model.pages[0].blocks[0].inlines[0]
    assert image.src == "/api/preview/assets/broken-image"
    assert "available" not in image.to_dict()


def test_preview_model_contains_inline_equation_mathml() -> None:
    model = build_preview_model(
        "Формула $e^{i\\pi}+1=0$ внутри строки.\n",
        _config(),
        RecordingStorage(),
    )

    paragraph = model.pages[0].blocks[0]
    equation = paragraph.inlines[1]

    assert paragraph.text == "Формула e^{i\\pi}+1=0 внутри строки."
    assert equation.kind == "inline_equation"
    assert equation.text == "e^{i\\pi}+1=0"
    assert equation.mathml is not None
    assert equation.mathml.startswith("<math")
    assert equation.diagnostic is None


def test_preview_model_contains_invalid_inline_equation_diagnostic() -> None:
    model = build_preview_model(
        "Плохая формула $\\frac$ не ломает preview.\n",
        _config(),
        RecordingStorage(),
    )

    equation = model.pages[0].blocks[0].inlines[1]

    assert equation.kind == "inline_equation"
    assert equation.mathml is None
    assert equation.diagnostic is not None
    assert "failed to convert LaTeX" in equation.diagnostic


def test_inline_image_paths_are_encoded_for_asset_endpoint() -> None:
    model = build_preview_model(
        "![Diagram](images/chapter-1/flow#1.png)\n",
        _config(),
        RecordingStorage(),
    )

    block = model.to_dict()["pages"][0]["blocks"][0]
    image_inline = block["inlines"][0]

    assert image_inline["asset_path"] == "images/chapter-1/flow#1.png"
    assert image_inline["src"] == ("/api/preview/assets/images%2Fchapter-1%2Fflow%231.png")


def test_image_inline_preserves_explicit_dimensions_without_storage_fetch() -> None:
    storage = RecordingStorage()

    model = build_preview_model(
        "![Sized](images/sized.png){width=320px height=180px}\n",
        _config(),
        storage,
    )

    assert storage.fetches == []
    block = model.to_dict()["pages"][0]["blocks"][0]
    image_inline = block["inlines"][0]
    assert image_inline["width"] == {"value": 320.0, "unit": "px"}
    assert image_inline["height"] == {"value": 180.0, "unit": "px"}
    assert image_inline["aspect_ratio"] == "320 / 180"


def test_inline_code_uses_configured_docx_text_and_style() -> None:
    cfg = _config(
        "overrides:\n"
        "  paragraph:\n"
        "    inline_code:\n"
        "      font: Courier New\n"
        "      size: 12pt\n"
        "      italic: true\n"
        "      quotes: true\n"
    )

    model = build_preview_model("Code `x-y`.\n", cfg, RecordingStorage())

    block = model.to_dict()["pages"][0]["blocks"][0]
    code_inline = block["inlines"][1]
    assert block["text"] == "Code «x‑y»."
    assert code_inline["text"] == "«x‑y»"
    assert code_inline["font_family"] == "Courier New"
    assert code_inline["font_size"] == "12pt"
    assert code_inline["italic"] is True


def test_filesystem_images_use_native_docx_size_metadata(tmp_path: Path) -> None:
    image_path = tmp_path / "portrait.png"
    Image.new("RGB", (100, 200), (0, 64, 128)).save(image_path)

    model = build_preview_model(
        "![Portrait](portrait.png)\n",
        _config(),
        FilesystemStorage(base_dir=tmp_path),
    )

    block = model.to_dict()["pages"][0]["blocks"][0]
    image_inline = block["inlines"][0]
    assert image_inline["width"] == {"value": 100.0, "unit": "pt"}
    assert image_inline["height"] == {"value": 200.0, "unit": "pt"}
    assert image_inline["aspect_ratio"] == "100 / 200"
    assert "base64" not in model.to_json().lower()


def test_standalone_image_paragraph_gets_numbered_image_block_caption() -> None:
    model = build_preview_model(
        "![Пейзаж](img-landscape.png)\n\n![Портрет](img-portrait.png)\n",
        _config(),
        RecordingStorage(),
    )

    blocks = model.pages[0].blocks

    assert [block.kind for block in blocks] == ["image", "image"]
    assert [block.number for block in blocks] == ["1", "2"]
    assert [block.caption for block in blocks] == [
        "Рисунок 1 — Пейзаж",
        "Рисунок 2 — Портрет",
    ]


def test_preview_model_contains_simple_table_rows_cells_and_caption() -> None:
    model = build_preview_model(
        "| Left | Center | Right |\n|:--|:-:|--:|\n| 1 | `two` | 3 |\n\n: Список значений\n",
        _config(),
        RecordingStorage(),
    )

    table = model.pages[0].blocks[0]

    assert table.kind == "table"
    assert table.number == "1"
    assert table.caption == "Таблица 1 — Список значений"
    assert table.text == "Left Center Right 1 two 3"
    assert table.rows is not None
    assert [row.header for row in table.rows] == [True, False]
    assert [cell.text for cell in table.rows[0].cells] == ["Left", "Center", "Right"]
    assert [cell.align for cell in table.rows[0].cells] == [
        "left",
        "center",
        "right",
    ]
    assert all(cell.header for cell in table.rows[0].cells)
    assert table.rows[1].cells[1].inlines[0].kind == "code"
    assert table.style["table_layout"] == "autofit"
    assert table.column_widths is not None
    assert [width.unit for width in table.column_widths] == ["pt", "pt", "pt"]
    assert round(sum(width.value for width in table.column_widths), 2) == 467.7


def test_preview_model_resolves_mixed_table_widths_from_content_area() -> None:
    model = build_preview_model(
        "| ID | Название | Описание |\n"
        "|----|----------|----------|\n"
        "| 1  | A        | B        |\n"
        '\n: Параметры {widths="3cm, auto, auto"}\n',
        _config(),
        RecordingStorage(),
    )

    table = model.pages[0].blocks[0]

    assert table.style["table_layout"] == "fixed"
    assert table.column_widths is not None
    assert [width.unit for width in table.column_widths] == ["pt", "pt", "pt"]
    assert table.column_widths[0].value == 85.05
    assert table.column_widths[1].value == 191.3
    assert table.column_widths[2].value == 191.3


def test_preview_model_numbers_bare_table_without_caption_text() -> None:
    model = build_preview_model(
        "| A |\n|---|\n| 1 |\n",
        _config(),
        RecordingStorage(),
    )

    table = model.pages[0].blocks[0]

    assert table.kind == "table"
    assert table.number == "1"
    assert table.caption == "Таблица 1"


def test_preview_model_contains_plain_listing_with_optional_caption() -> None:
    model = build_preview_model(
        "```python\nprint(1)\n```\n\n: Пример\n",
        _config(),
        RecordingStorage(),
    )

    listing = model.pages[0].blocks[0]

    assert listing.kind == "listing"
    assert listing.number == "1"
    assert listing.caption == "Листинг 1 — Пример"
    assert listing.language == "python"
    assert listing.text == "print(1)\n"
    assert listing.style["font_family"] == "Consolas"
    assert listing.style["font_size"] == "12pt"
    assert listing.continuation is False


def test_preview_model_contains_highlighted_listing_tokens() -> None:
    cfg = _config("overrides:\n  listing:\n    syntax_highlighting: true\n")

    model = build_preview_model(
        "```python\ndef f():\n    return 1\n```\n\n: Пример\n",
        cfg,
        RecordingStorage(),
    )

    listing = model.pages[0].blocks[0]

    assert listing.kind == "listing"
    assert listing.inlines
    assert any(inline.text == "def" for inline in listing.inlines)
    assert any(inline.color is not None for inline in listing.inlines)


def test_long_native_listing_is_split_into_page_owned_preview_chunks() -> None:
    lines = [f"line_{index:02d} = {index}" for index in range(1, 71)]
    code = "\n".join(lines)

    model = build_preview_model(
        f"```python\n{code}\n```\n\n: Long module\n",
        _config(),
        RecordingStorage(),
    )

    listings = [block for page in model.pages for block in page.blocks if block.kind == "listing"]
    assert model.total_pages == 2
    assert len(listings) == 2
    assert [listing.page for listing in listings] == [1, 2]
    assert [listing.continuation for listing in listings] == [False, True]
    assert listings[0].caption == "Листинг 1 — Long module"
    assert listings[1].caption is None
    assert "".join(listing.text for listing in listings) == code + "\n"


def test_highlighted_listing_spacing_is_reserved_in_page_chunks() -> None:
    lines = [f"line_{index:02d} = {index}" for index in range(1, 71)]
    code = "\n".join(lines)
    spaced = build_preview_model(
        f"```python\n{code}\n```\n\n: Long module\n",
        _config(
            "overrides:\n"
            "  listing:\n"
            "    syntax_highlighting: true\n"
            "    space_before: 18pt\n"
            "    space_after: 18pt\n"
        ),
        RecordingStorage(),
    )

    listings = [block for page in spaced.pages for block in page.blocks if block.kind == "listing"]

    assert len(listings) > 1
    assert listings[0].style["space_before"] == "0pt"
    assert listings[0].style["space_after"] == "0pt"
    assert listings[0].style["caption_space_before"] == "18pt"
    assert listings[-1].style["space_before"] == "0pt"
    assert listings[-1].style["space_after"] == "18pt"
    assert "".join(block.text for block in listings) == code + "\n"


def test_highlighted_listing_footer_clearance_is_reserved_before_following_content() -> None:
    code = "\n".join(f"line_{index:02d} = {index}" for index in range(1, 45))
    model = build_preview_model(
        f"```python\n{code}\n```\n\n: Long module\n\nFollowing paragraph.\n",
        _config("overrides:\n  listing:\n    syntax_highlighting: true\n"),
        RecordingStorage(),
    )

    listing = next(
        block for page in model.pages for block in page.blocks if block.kind == "listing"
    )
    following = next(
        block
        for page in model.pages
        for block in page.blocks
        if block.text == "Following paragraph."
    )

    assert listing.page == 1
    assert following.page == 2


def test_preview_model_contains_numbered_block_equations() -> None:
    model = build_preview_model(
        "$$ x=1 $$\n\n$$ y=2 $$\n",
        _config(),
        RecordingStorage(),
    )

    equations = model.pages[0].blocks

    assert [block.kind for block in equations] == ["equation", "equation"]
    assert [block.number for block in equations] == ["1", "2"]
    assert equations[0].mathml is not None
    assert equations[0].mathml.startswith("<math")
    assert equations[0].diagnostic is None


def test_preview_model_block_equation_uses_configured_style() -> None:
    cfg = _config(
        "overrides:\n"
        "  equation:\n"
        "    space_before: 6pt\n"
        "    space_after: 9pt\n"
        "    numbering_alignment: left\n"
        "    parentheses: false\n"
    )

    model = build_preview_model("$$ a=b $$\n", cfg, RecordingStorage())
    equation = model.pages[0].blocks[0]

    assert equation.kind == "equation"
    assert equation.number == "1"
    assert equation.style["padding_before"] == "6pt"
    assert equation.style["padding_after"] == "9pt"
    assert equation.style["space_before"] == "0pt"
    assert equation.style["space_after"] == "0pt"
    assert equation.style["numbering_alignment"] == "left"
    assert equation.style["parentheses"] is False


def test_preview_model_invalid_block_equation_has_diagnostic() -> None:
    model = build_preview_model("$$ \\frac $$\n", _config(), RecordingStorage())
    equation = model.pages[0].blocks[0]

    assert equation.kind == "equation"
    assert equation.mathml is None
    assert equation.diagnostic is not None
    assert "failed to convert LaTeX" in equation.diagnostic


def test_preview_model_contains_unordered_list_items_with_configured_markers() -> None:
    cfg = _config(
        "overrides:\n"
        "  lists:\n"
        '    bullet_marker: "*"\n'
        "    indent_left: 2cm\n"
        "    indent_per_level: 1cm\n"
    )

    model = build_preview_model("- One\n- Two\n", cfg, RecordingStorage())

    blocks = model.pages[0].blocks
    assert [block.kind for block in blocks] == ["list_item", "list_item"]
    assert [block.marker for block in blocks] == ["*", "*"]
    assert [block.text for block in blocks] == ["One", "Two"]
    assert [block.level for block in blocks] == [1, 1]
    assert blocks[0].list_type == "unordered"
    assert blocks[0].style["margin_left"] == "2cm"
    assert blocks[0].style["text_indent"] == "-1cm"
    assert blocks[0].style["line_spacing"] == cfg.font.line_spacing


def test_preview_model_uses_docx_compatible_markers_for_nested_bullet_lists() -> None:
    markdown = "- One\n    - Deep\n    - Deeper\n- Two\n"

    model = build_preview_model(markdown, _config(), RecordingStorage())

    list_blocks = [block for block in model.pages[0].blocks if block.kind == "list_item"]

    assert [block.marker for block in list_blocks] == ["—", "1)", "2)", "—"]
    assert [block.level for block in list_blocks] == [1, 2, 2, 1]
    assert [block.list_type for block in list_blocks] == ["unordered"] * 4
    assert [block.marker_separator for block in list_blocks] == ["", "", "", ""]
    assert {block.style.get("marker_width") for block in list_blocks} == {"0.75cm"}


def test_preview_model_nested_bullet_under_ordered_list_is_fresh_level_one() -> None:
    markdown = "1. A\n    - Deep\n    - Deeper\n2. B\n"

    model = build_preview_model(markdown, _config(), RecordingStorage())

    list_blocks = [block for block in model.pages[0].blocks if block.kind == "list_item"]

    assert [block.marker for block in list_blocks] == ["1.", "—", "—", "2."]


def test_preview_model_nested_bullets_use_bullet_marker_in_inline_mode() -> None:
    cfg = _config(
        "overrides:\n"
        "  lists:\n"
        "    mode: inline\n"
    )

    model = build_preview_model("- One\n    - Deep\n    - Deeper\n- Two\n", cfg, RecordingStorage())

    list_blocks = [block for block in model.pages[0].blocks if block.kind == "list_item"]

    assert [block.marker for block in list_blocks] == ["—", "—", "—", "—"]
    assert [block.level for block in list_blocks] == [1, 2, 2, 1]
    assert [block.marker_separator for block in list_blocks] == ["\t", "\t", "\t", "\t"]
    assert all("marker_width" not in block.style for block in list_blocks)


def test_organic_pagination_reserves_docx_page_edge_leading() -> None:
    markdown = "\n".join(f"{index}. Item {index}" for index in range(1, 32))

    model = build_preview_model(markdown + "\n", _config(), RecordingStorage())

    assert model.total_pages == 2
    assert len(model.pages[0].blocks) == 29
    assert model.pages[0].blocks[-1].marker == "29."
    assert model.pages[1].blocks[0].marker == "30."


def test_preview_model_uses_docx_compatible_ordered_markers_for_nested_lists() -> None:
    markdown = (
        "1. A\n    1. X\n    2. Y\n2. B\n\n<!-- separate -->\n\n"
        '1. Alpha\n2. Beta\n{marker="lower-alpha-ru"}\n'
    )

    model = build_preview_model(markdown, _config(), RecordingStorage())

    list_blocks = [
        block for page in model.pages for block in page.blocks if block.kind == "list_item"
    ]

    assert [block.marker for block in list_blocks] == [
        "1.",
        "1.1.",
        "1.2.",
        "2.",
        "а)",
        "б)",
    ]
    assert [block.marker_separator for block in list_blocks[:4]] == ["", "", "", ""]
    assert [block.style.get("marker_width") for block in list_blocks[:4]] == ["0.75cm"] * 4
    assert [block.level for block in list_blocks[:4]] == [1, 2, 2, 1]
    assert list_blocks[1].style["margin_left"] == "2cm"
    assert list_blocks[3].marker == "2."
