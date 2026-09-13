"""UI-метаданные в ``schema.yaml`` шаблонов (T027).

Проверяем, что:

* ``ui:`` per-field прокидывается в JSON Schema (``title``/``description``,
  расширения ``x-group``/``x-order``);
* top-level ``groups:`` доходит до корня JSON Schema (``x-groups``);
* отсутствие ``ui:`` и ``groups:`` не ломает обратную совместимость.
"""

from __future__ import annotations

from markdown_gost.templates._schema import schema_from_dict


def test_ui_label_and_description_become_jsonschema_title_and_description() -> None:
    model = schema_from_dict(
        {
            "fields": {
                "title": {
                    "type": "str",
                    "default": "",
                    "ui": {
                        "label": "Тема работы",
                        "description": "Полное название как в задании",
                    },
                },
            },
        }
    )
    schema = model.model_json_schema()
    title_prop = schema["properties"]["title"]
    assert title_prop["title"] == "Тема работы"
    assert title_prop["description"] == "Полное название как в задании"


def test_ui_group_and_order_become_x_extensions() -> None:
    model = schema_from_dict(
        {
            "fields": {
                "title": {
                    "type": "str",
                    "default": "",
                    "ui": {
                        "label": "Тема",
                        "group": "main",
                        "order": 10,
                    },
                },
            },
        }
    )
    title_prop = model.model_json_schema()["properties"]["title"]
    assert title_prop["x-group"] == "main"
    assert title_prop["x-order"] == 10


def test_top_level_groups_reach_jsonschema_root() -> None:
    model = schema_from_dict(
        {
            "groups": [
                {"id": "main", "label": "Основное", "order": 10},
                {"id": "extra", "label": "Дополнительно", "order": 20},
            ],
            "fields": {
                "title": {"type": "str", "default": ""},
            },
        }
    )
    schema = model.model_json_schema()
    assert schema["x-groups"] == [
        {"id": "main", "label": "Основное", "order": 10},
        {"id": "extra", "label": "Дополнительно", "order": 20},
    ]


def test_no_ui_metadata_keeps_backward_compatibility() -> None:
    model = schema_from_dict(
        {
            "fields": {
                "title": {"type": "str", "default": ""},
            },
        }
    )
    schema = model.model_json_schema()
    title_prop = schema["properties"]["title"]
    assert "x-group" not in title_prop
    assert "x-order" not in title_prop
    assert "x-groups" not in schema


def test_ui_unknown_keys_are_ignored_silently() -> None:
    """``ui:`` — расширяемый словарь; неизвестные ключи не должны падать.

    Это даёт пространство добавлять новые UI-хинты (например, ``placeholder``)
    без правок в ядре сейчас.
    """

    model = schema_from_dict(
        {
            "fields": {
                "title": {
                    "type": "str",
                    "default": "",
                    "ui": {
                        "label": "Тема",
                        "placeholder": "Введите название",  # пока не известен
                    },
                },
            },
        }
    )
    title_prop = model.model_json_schema()["properties"]["title"]
    assert title_prop["title"] == "Тема"
    # Неизвестный UI-хинт сохраняем как ``x-<key>`` чтобы фронт мог использовать,
    # не дожидаясь обновлений ядра.
    assert title_prop["x-placeholder"] == "Введите название"


def test_required_field_with_ui() -> None:
    """``ui:`` совместимо с ``required: true``."""

    model = schema_from_dict(
        {
            "fields": {
                "title": {
                    "type": "str",
                    "required": True,
                    "ui": {"label": "Тема"},
                },
            },
        }
    )
    schema = model.model_json_schema()
    assert "title" in schema.get("required", [])
    assert schema["properties"]["title"]["title"] == "Тема"
