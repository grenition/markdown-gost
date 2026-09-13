from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from markdown_gost.config.errors import UnknownPresetError
from markdown_gost.config.schema import Config


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in overrides.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result


def _load_preset(name: str) -> dict[str, Any]:
    try:
        text = (
            resources.files("markdown_gost.config.presets")
            .joinpath(f"{name}.yaml")
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, IsADirectoryError, ModuleNotFoundError) as e:
        raise UnknownPresetError(name) from e
    parsed = yaml.safe_load(text)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise UnknownPresetError(name)
    return parsed


def load_config_from_string(content: str) -> Config:
    user = yaml.safe_load(content)
    if not isinstance(user, dict):
        return Config.model_validate(user if user is not None else {})

    preset_name = user.get("preset")
    if not isinstance(preset_name, str) or not preset_name:
        return Config.model_validate(user)

    preset_data = _load_preset(preset_name)
    overrides = user.get("overrides") or {}
    if not isinstance(overrides, dict):
        return Config.model_validate({"preset": preset_name, "overrides": overrides})

    merged = _deep_merge(preset_data, overrides)
    merged["preset"] = preset_name
    return Config.model_validate(merged)


def load_config_from_path(path: Path) -> Config:
    return load_config_from_string(path.read_text(encoding="utf-8"))
