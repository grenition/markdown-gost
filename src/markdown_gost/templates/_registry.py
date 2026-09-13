"""Реестр шаблонов — внутренняя реализация.

Публичный API живёт в :mod:`markdown_gost.templates`. Здесь — структура хранения
зарегистрированных шаблонов и резолвер ленивых ``render_fn``.

Шаблон описывается тремя сущностями:

* ``name`` — идентификатор, по которому AST-узел ``TemplateBlock(name=...)``
  ищет реализацию.
* ``schema`` — pydantic-модель параметров (источник правды о допустимых полях).
* ``render_fn`` — фабрика ``Renderable``: ``(params, ctx) -> Renderable``.
  Может быть передана в виде callable или строки ``"package.module:attr"``,
  тогда импорт откладывается до первого вызова.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from markdown_gost.renderable.base import Renderable

RenderFn = Callable[[dict[str, Any], Any], Renderable]
RenderFnSpec = RenderFn | str
PreviewRenderFn = Callable[[dict[str, Any], Any], None]
PreviewRenderFnSpec = PreviewRenderFn | str


@dataclass
class _Template:
    """Внутренняя запись в реестре.

    ``_render_fn`` хранится как callable или строка-спека для ленивого импорта;
    после первого резолва кэшируется в ``_resolved``.
    """

    name: str
    schema: type[BaseModel]
    _render_fn: RenderFnSpec
    _preview_fn: PreviewRenderFnSpec | None = None
    _resolved: RenderFn | None = None
    _preview_resolved: PreviewRenderFn | None = None

    def render_fn(self) -> RenderFn:
        if self._resolved is not None:
            return self._resolved
        spec = self._render_fn
        if callable(spec):
            self._resolved = spec
            return spec
        if not isinstance(spec, str) or ":" not in spec:
            raise ValueError(
                f"render_fn for template {self.name!r} must be callable or "
                f"'module.path:attr' string, got {spec!r}"
            )
        module_name, attr = spec.split(":", 1)
        module = importlib.import_module(module_name)
        fn = getattr(module, attr)
        if not callable(fn):
            raise TypeError(
                f"render_fn {spec!r} for template {self.name!r} is not callable"
            )
        resolved: RenderFn = fn
        self._resolved = resolved
        return resolved

    def preview_fn(self) -> PreviewRenderFn | None:
        if self._preview_fn is None:
            return None
        if self._preview_resolved is not None:
            return self._preview_resolved
        spec = self._preview_fn
        if callable(spec):
            self._preview_resolved = spec
            return spec
        if not isinstance(spec, str) or ":" not in spec:
            raise ValueError(
                f"preview_fn for template {self.name!r} must be callable or "
                f"'module.path:attr' string, got {spec!r}"
            )
        module_name, attr = spec.split(":", 1)
        module = importlib.import_module(module_name)
        fn = getattr(module, attr)
        if not callable(fn):
            raise TypeError(
                f"preview_fn {spec!r} for template {self.name!r} is not callable"
            )
        resolved: PreviewRenderFn = fn
        self._preview_resolved = resolved
        return resolved


_REGISTRY: dict[str, _Template] = {}


def _store(
    name: str,
    render_fn: RenderFnSpec,
    schema: type[BaseModel],
    *,
    preview_fn: PreviewRenderFnSpec | None = None,
) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("template name must be a non-empty string")
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        raise TypeError("schema must be a pydantic BaseModel subclass")
    _REGISTRY[name] = _Template(
        name=name,
        schema=schema,
        _render_fn=render_fn,
        _preview_fn=preview_fn,
    )


def _get(name: str) -> _Template | None:
    return _REGISTRY.get(name)


def _list_names() -> list[str]:
    return sorted(_REGISTRY)


def _drop(name: str) -> None:
    _REGISTRY.pop(name, None)
