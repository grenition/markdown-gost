"""UI-метаданные на полях ``Config`` (T028).

Каждое top-level поле должно иметь человеческий ``title`` (label) и
``description``, а корень JSON Schema — список секций ``x-groups`` для
ordered-рендеринга формы.
"""

from __future__ import annotations

from pathlib import Path

from markdown_gost.config.schema import Config


def test_top_level_sections_have_titles() -> None:
    schema = Config.model_json_schema()
    properties = schema["properties"]
    # Все секции имеют человеческий label.
    for section in (
        "page",
        "font",
        "paragraph",
        "headings",
        "captions",
        "table",
        "listing",
        "lists",
        "equation",
    ):
        prop = properties[section]
        assert prop.get("title"), f"section {section!r} missing title"


def test_root_has_x_groups_ordered() -> None:
    schema = Config.model_json_schema()
    groups = schema["x-groups"]
    assert isinstance(groups, list)
    ids = [g["id"] for g in groups]
    # Все секции входят в groups.
    for section in (
        "page",
        "font",
        "paragraph",
        "headings",
        "captions",
        "table",
        "listing",
        "lists",
        "equation",
    ):
        assert section in ids
    # Каждая группа имеет id, label, order.
    for g in groups:
        assert {"id", "label", "order"} <= set(g)
    # Order — целые, монотонно растёт.
    orders = [g["order"] for g in groups]
    assert orders == sorted(orders)


def test_inner_field_has_title_and_description() -> None:
    """Маркер: проверим парочку «глубоких» полей, чтобы убедиться что
    лейблы прокинуты не только на корневые секции."""

    schema = Config.model_json_schema()
    defs = schema["$defs"]
    page_props = defs["Page"]["properties"]
    assert page_props["size"].get("title"), "Page.size missing title"
    assert page_props["size"].get("description"), "Page.size missing description"

    font_props = defs["Font"]["properties"]
    assert font_props["family"].get("title"), "Font.family missing title"


def test_all_public_config_fields_have_ui_metadata() -> None:
    schema = Config.model_json_schema()
    groups = {group["id"] for group in schema["x-groups"]}
    objects = {"Config": schema, **schema["$defs"]}

    for object_name, object_schema in objects.items():
        properties = object_schema.get("properties")
        if not properties:
            continue

        for field_name, field_schema in properties.items():
            path = f"{object_name}.{field_name}"
            assert field_schema.get("title"), f"{path} missing title"
            assert field_schema.get("description"), f"{path} missing description"
            group = field_schema.get("x-group")
            order = field_schema.get("x-order")
            assert group in groups, f"{path} missing known x-group"
            assert isinstance(order, int), f"{path} missing integer x-order"


def test_config_reference_does_not_document_removed_fields() -> None:
    text = (
        Path(__file__).parents[3].joinpath("docs/config-reference.md").read_text(encoding="utf-8")
    )

    assert "continuation_label" not in text
    assert "continuation_label_enabled" not in text


def test_preset_field_is_present_with_title() -> None:
    schema = Config.model_json_schema()
    preset = schema["properties"]["preset"]
    assert preset.get("title")


def test_font_family_fields_are_enums() -> None:
    """``Font.family``, ``InlineCode.font`` и ``ListingFont.family`` —
    Literal-enum'ы, чтобы UI рисовал дропдаун из фиксированного списка
    шрифтов вместо свободного текстового поля."""

    schema = Config.model_json_schema()
    defs = schema["$defs"]
    cases = [
        defs["Font"]["properties"]["family"],
        defs["InlineCode"]["properties"]["font"],
        defs["ListingFont"]["properties"]["family"],
    ]
    for node in cases:
        assert isinstance(node.get("enum"), list) and len(node["enum"]) >= 5, (
            f"font field {node.get('title')!r} should be a non-trivial enum"
        )


def test_captions_continuation_break_is_shared_bool_default_false() -> None:
    """Подпись «Продолжение» — общий для таблиц и листингов тогглер
    ``captions.continuation_break: bool`` (UI рендерит галочку). По
    умолчанию выключен — Word/LO ломают элементы сам. Per-element-поля
    (``captions.table.continuation_label`` и т.д.) и парный
    ``listing.continuation_label_enabled`` должны быть удалены, чтобы
    UI не дублировал одну и ту же настройку."""

    schema = Config.model_json_schema()
    defs = schema["$defs"]
    captions = defs["Captions"]["properties"]
    assert "continuation_break" in captions, "captions.continuation_break must exist"
    cb = captions["continuation_break"]
    assert cb.get("type") == "boolean", "continuation_break must be a boolean toggle"
    assert cb.get("default") is False, "default must be off (manual breaks opt-in)"
    # Старого строкового поля больше нет.
    assert "continuation_label" not in captions, (
        "captions.continuation_label was replaced with continuation_break (bool)"
    )
    # CaptionStyle не несёт continuation_label.
    cs = defs["CaptionStyle"]["properties"]
    assert "continuation_label" not in cs, (
        "CaptionStyle.continuation_label must be removed (replaced by captions.continuation_break)"
    )
    # Listing не несёт continuation_label_enabled.
    listing = defs["Listing"]["properties"]
    assert "continuation_label_enabled" not in listing, (
        "Listing.continuation_label_enabled must be removed "
        "(use captions.continuation_break instead)"
    )


def test_enum_fields_carry_x_enum_labels() -> None:
    """Все enum-поля в форме UI должны нести ``x-enum-labels`` —
    словарь {значение: русский лейбл}, чтобы клиент рендерил селекторы
    в человеческом виде, а не значениями ``portrait``/``landscape``."""

    schema = Config.model_json_schema()
    defs = schema["$defs"]

    cases = [
        (defs["Page"]["properties"]["size"], {"A4", "A3", "Letter"}),
        (defs["Page"]["properties"]["orientation"], {"portrait", "landscape"}),
        (
            defs["Paragraph"]["properties"]["alignment"],
            {"left", "right", "center", "justify"},
        ),
        (
            defs["HeadingLevel"]["properties"]["alignment"],
            {"left", "right", "center", "justify"},
        ),
        (
            defs["Headings"]["properties"]["numbering"],
            {"continuous", "per-section", "none"},
        ),
        (
            defs["CaptionStyle"]["properties"]["alignment"],
            {"left", "right", "center", "justify"},
        ),
        (
            defs["Equation"]["properties"]["numbering_alignment"],
            {"left", "right", "center", "justify"},
        ),
    ]
    for node, expected_values in cases:
        labels = node.get("x-enum-labels")
        assert isinstance(labels, dict), f"missing x-enum-labels on {node.get('title')!r}"
        assert set(labels) == expected_values, (
            f"x-enum-labels keys mismatch for {node.get('title')!r}: "
            f"have {set(labels)}, expected {expected_values}"
        )
        # Лейблы — непустые строки.
        for value, label in labels.items():
            assert isinstance(label, str) and label.strip(), (
                f"empty label for {value!r} in {node.get('title')!r}"
            )
