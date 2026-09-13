"""Сборка pydantic-модели параметров шаблона из ``schema.yaml``.

YAML-формат — единственный источник правды о параметрах шаблона
(см. ADR-0005 и notes T022). Пример::

    groups:                          # T027: опциональные группы для UI
      - id: main
        label: "Основное"
        order: 10
    fields:
      title:
        type: str
        required: true
        ui:                          # T027: метаданные для UI-формы
          label: "Тема работы"
          description: "Полное название"
          group: main
          order: 10
      authors:
        type: list[str]
        default: []
      year:
        type: int
        default: null
    strict: true   # extra fields forbidden (по-умолчанию true)

Поддерживаемые типы: ``str``, ``int``, ``float``, ``bool``, ``dict``, ``any``,
а также ``list[<type>]`` для перечисленных. Этого достаточно для MVP-шаблонов
(titlepage, content). Расширение типов — по мере появления новых шаблонов.

UI-метаданные (``ui:`` и ``groups:``) необязательны и попадают в JSON Schema
сгенерированной модели: ``label``/``description`` — стандартные
``title``/``description``, остальные ключи — расширения ``x-<key>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.json_schema import JsonSchemaValue

_SCALAR_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "any": object,
}

_MISSING = object()
# Ключи ``ui:``, которые маппятся на стандартные поля JSON Schema.
_UI_STANDARD_KEYS = {"label": "title", "description": "description"}


def _resolve_type(spec: str) -> Any:
    spec = spec.strip()
    if spec.startswith("list[") and spec.endswith("]"):
        inner = spec[len("list[") : -1].strip()
        inner_type = _resolve_type(inner)
        return list[inner_type]  # type: ignore[valid-type]
    if spec in _SCALAR_TYPES:
        return _SCALAR_TYPES[spec]
    raise ValueError(f"unsupported field type in schema.yaml: {spec!r}")


def _build_field_kwargs(ui: dict[str, Any] | None) -> dict[str, Any]:
    """Преобразовать ``ui:`` в kwargs для :func:`pydantic.Field`.

    ``label``/``description`` идут на стандартные ``title``/``description``,
    остальные ключи — в ``json_schema_extra`` как ``x-<key>``.
    """

    if not ui:
        return {}
    if not isinstance(ui, dict):
        raise ValueError("`ui` must be a mapping")

    kwargs: dict[str, Any] = {}
    extras: dict[str, Any] = {}
    for key, value in ui.items():
        if key in _UI_STANDARD_KEYS:
            kwargs[_UI_STANDARD_KEYS[key]] = value
        else:
            extras[f"x-{key}"] = value
    if extras:
        kwargs["json_schema_extra"] = extras
    return kwargs


def _normalize_groups(raw: Any) -> list[dict[str, Any]] | None:
    """Валидируем ``groups:`` и нормализуем порядок ключей.

    Каждая группа — словарь с обязательным ``id`` и ``label`` и опциональным
    ``order``. Полученный список идёт в JSON Schema корня как ``x-groups``,
    фронт сам сортирует по ``order`` и группирует поля по ``x-group`` каждого
    свойства.
    """

    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("`groups` must be a list")
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each group must be a mapping")
        if "id" not in entry or "label" not in entry:
            raise ValueError("group must have `id` and `label`")
        normalized: dict[str, Any] = {"id": entry["id"], "label": entry["label"]}
        if "order" in entry:
            normalized["order"] = entry["order"]
        out.append(normalized)
    return out


def schema_from_dict(
    data: dict[str, Any],
    *,
    model_name: str = "TemplateParams",
) -> type[BaseModel]:
    """Собрать pydantic-модель из словаря (распарсенного schema.yaml)."""

    if not isinstance(data, dict):
        raise ValueError("schema must be a mapping at the top level")
    fields_raw = data.get("fields") or {}
    if not isinstance(fields_raw, dict):
        raise ValueError("`fields` must be a mapping")
    strict = bool(data.get("strict", True))
    groups = _normalize_groups(data.get("groups"))

    fields: dict[str, Any] = {}
    for name, spec in fields_raw.items():
        if not isinstance(spec, dict):
            raise ValueError(f"field {name!r}: spec must be a mapping")
        type_str = spec.get("type")
        if not isinstance(type_str, str):
            raise ValueError(f"field {name!r}: missing or non-string `type`")
        py_type = _resolve_type(type_str)
        required = bool(spec.get("required", "default" not in spec))
        default = spec.get("default", _MISSING)
        ui_kwargs = _build_field_kwargs(spec.get("ui"))
        if required:
            fields[name] = (py_type, Field(..., **ui_kwargs))
        else:
            if default is _MISSING:
                default = None
                py_type = py_type | None
            if ui_kwargs:
                fields[name] = (py_type, Field(default=default, **ui_kwargs))
            else:
                fields[name] = (py_type, default)

    if groups is not None:
        # ``json_schema_extra`` на ``model_config`` мерджится в корень
        # сгенерированного JSON Schema — фронт получает ``x-groups`` рядом
        # с ``properties``.
        base_config = ConfigDict(
            extra="forbid" if strict else "allow",
            json_schema_extra=cast("JsonSchemaValue", {"x-groups": groups}),
        )
    else:
        base_config = ConfigDict(extra="forbid" if strict else "allow")

    class _Base(BaseModel):
        model_config = base_config

    model = create_model(model_name, __base__=_Base, **fields)
    return model


def schema_from_yaml(
    path: Path | str,
    *,
    model_name: str = "TemplateParams",
) -> type[BaseModel]:
    """Прочитать ``schema.yaml`` и вернуть pydantic-модель."""

    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return schema_from_dict(data, model_name=model_name)
