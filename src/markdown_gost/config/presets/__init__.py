"""Packaged config presets (``*.yaml`` files next to this module)."""

from __future__ import annotations

from importlib import resources

_SUFFIX = ".yaml"


def available_presets() -> tuple[str, ...]:
    """Sorted names of the packaged presets, e.g. ``("gost-7-32-2017",)``."""
    return tuple(
        sorted(
            entry.name[: -len(_SUFFIX)]
            for entry in resources.files(__package__ or __name__).iterdir()
            if entry.name.endswith(_SUFFIX) and entry.is_file()
        )
    )
