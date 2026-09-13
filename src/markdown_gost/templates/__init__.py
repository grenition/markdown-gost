"""Реестр шаблонов оформления (T022).

Шаблон — это именованная единица вёрстки (титульник, оглавление, разделитель),
вызываемая из markdown через ``---name`` (см. ``ast.TemplateBlock``). Реестр
абстрагирован от способа реализации: поверх низкоуровневого ``register`` могут
жить декларативные провайдеры и автоматический extractor из пользовательских
DOCX (post-MVP). См. ``docs/templates-guide.md``.

Публичный API::

    register(name, render_fn, schema)   # регистрация
    list_templates()                    # имена всех шаблонов
    render_template(name, params, parent)  # AST → Renderable
    schema_from_yaml(path)              # собрать pydantic-модель из schema.yaml
    TemplateContext(document, config)   # контекст рендера, передаётся в render_fn

Все известные шаблоны импортируются здесь же — по принципу «явная регистрация
через import» (см. T022). Реальные шаблоны добавляются в T023.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from docx.document import Document as DocxDocument
from pydantic import BaseModel, ValidationError

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.renderable.base import Renderable

from . import _registry
from ._placeholder import make_placeholder
from ._preview import PreviewTemplateContext
from ._registry import PreviewRenderFn, PreviewRenderFnSpec, RenderFn, RenderFnSpec
from ._schema import schema_from_dict, schema_from_yaml

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "PreviewRenderFn",
    "PreviewRenderFnSpec",
    "PreviewTemplateContext",
    "RenderFn",
    "RenderFnSpec",
    "TemplateContext",
    "get_template_schema",
    "list_templates",
    "register",
    "render_preview_template",
    "render_template",
    "schema_from_dict",
    "schema_from_yaml",
    "unregister",
]


@dataclass(frozen=True)
class TemplateContext:
    """Контекст рендера шаблона.

    Прокидывается в ``render_fn(params, parent)`` как ``parent``. Содержит
    минимально необходимое: docx-документ (как parent для python-docx),
    активный :class:`Config` и AST документа (нужен шаблонам, которым
    важен полный план документа — например, ``content`` сканирует заголовки
    заранее, чтобы зарезервировать высоту под TOC). Расширение полей —
    без слома существующих шаблонов: новые поля только с дефолтами.
    """

    document: DocxDocument
    config: Config
    document_ast: ast.Document = field(default_factory=ast.Document)


def register(
    name: str,
    render_fn: RenderFnSpec,
    schema: type[BaseModel],
    *,
    preview_fn: PreviewRenderFnSpec | None = None,
) -> None:
    """Зарегистрировать шаблон.

    ``render_fn`` — либо callable ``(params, parent) -> Renderable``, либо
    строка вида ``"package.module:attr"`` для отложенного импорта (полезно,
    чтобы не тащить тяжёлые зависимости шаблона при `import markdown_gost`).

    ``schema`` — pydantic-модель параметров. Получить её можно либо вручную
    (subclass ``BaseModel``), либо через :func:`schema_from_yaml`. Список
    параметров живёт **только** в schema — дублировать его в ``render.py``
    запрещено (см. notes T022).
    """

    _registry._store(name, render_fn, schema, preview_fn=preview_fn)


def unregister(name: str) -> None:
    """Удалить шаблон из реестра. Тихо игнорирует отсутствующие имена."""

    _registry._drop(name)


def list_templates() -> list[str]:
    """Список зарегистрированных имён (отсортирован)."""

    return _registry._list_names()


def get_template_schema(name: str) -> type[BaseModel] | None:
    """Вернуть pydantic-модель параметров шаблона.

    Используется HTTP API (T027) для генерации JSON Schema. ``None`` если
    шаблона с таким именем нет — без исключения, чтобы вызывающий мог сам
    решить, как реагировать (404 в API, плейсхолдер в рендере).
    """

    template = _registry._get(name)
    return template.schema if template is not None else None


def render_template(
    name: str,
    params: dict[str, Any],
    parent: TemplateContext,
) -> Renderable:
    """Отрендерить шаблон в :class:`Renderable`.

    Если шаблон не найден или параметры не проходят валидацию — возвращается
    красный плейсхолдер с warning-логом. Этот метод никогда не бросает: лучше
    видимый маркер в документе, чем падение всего рендера.
    """

    template = _registry._get(name)
    if template is None:
        return make_placeholder(
            parent.document,
            parent.config,
            template_name=name,
            reason="template not registered",
        )
    try:
        validated = template.schema.model_validate(params)
    except ValidationError as exc:
        return make_placeholder(
            parent.document,
            parent.config,
            template_name=name,
            reason=f"invalid params ({exc.error_count()} error(s))",
        )
    try:
        render_fn = template.render_fn()
    except Exception as exc:
        return make_placeholder(
            parent.document,
            parent.config,
            template_name=name,
            reason=f"render_fn import failed: {exc}",
        )
    return render_fn(validated.model_dump(), parent)


def render_preview_template(
    name: str,
    params: dict[str, Any],
    parent: PreviewTemplateContext,
) -> str | None:
    """Dispatch a registered template to its native preview handler.

    The result is a diagnostic string instead of an exception so the caller can
    keep the preview visible when a template is unknown, invalid, or lacks a
    preview implementation.
    """

    template = _registry._get(name)
    if template is None:
        return "template not registered"
    try:
        validated = template.schema.model_validate(params)
    except ValidationError as exc:
        return f"invalid params ({exc.error_count()} error(s))"
    try:
        preview_fn = template.preview_fn()
    except Exception:
        _LOGGER.exception("Preview renderer import failed for template %r", name)
        return "preview renderer unavailable"
    if preview_fn is None:
        return "preview renderer not registered"
    try:
        preview_fn(validated.model_dump(), parent)
    except Exception:
        _LOGGER.exception("Preview rendering failed for template %r", name)
        return "preview rendering failed"
    return None


# Авто-регистрация встроенных шаблонов: import-time side-effect через
# подмодули. Конкретные шаблоны живут в собственных пакетах, а здесь мы
# просто импортируем их, чтобы `register(...)` отработал.
from . import content as _content  # noqa: E402, F401
from . import titlepage_university as _titlepage_university  # noqa: E402, F401
