"""JSON-safe values shared by preview extensions and their model."""

from __future__ import annotations

import math
from typing import Any

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]


def copy_json_style(style: dict[Any, Any] | None) -> dict[str, JsonPrimitive] | None:
    """Return an independent JSON-primitive style mapping for preview blocks."""

    if style is None:
        return None
    copied: dict[str, JsonPrimitive] = {}
    for key, value in style.items():
        if not isinstance(key, str):
            raise ValueError("style keys must be strings")
        if (
            value is None
            or isinstance(value, str | int | bool)
            or (isinstance(value, float) and math.isfinite(value))
        ):
            copied[key] = value
        else:
            raise ValueError("style values must be finite JSON primitives")
    return copied


def copy_json_layout(layout: dict[Any, Any] | None) -> dict[str, JsonValue] | None:
    """Return an independent, strictly JSON-safe copy of extension layout data."""

    if layout is None:
        return None
    value = _copy_json_value(layout)
    if not isinstance(value, dict):  # pragma: no cover - guarded by the input type.
        raise ValueError("layout must be a JSON object")
    return value


def _copy_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("layout must not contain non-finite numbers")
        return value
    if isinstance(value, list):
        return [_copy_json_value(item) for item in value]
    if isinstance(value, dict):
        copied: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("layout object keys must be strings")
            copied[key] = _copy_json_value(item)
        return copied
    raise ValueError("layout must contain only JSON values")
