"""Шаблон ``titlepage-university`` — титульный лист по типовой университетской форме РФ (T023).

Вуз задаётся параметрами ``university_full`` / ``university_short``; эмблема —
параметром ``logo`` (путь или http(s)-ссылка). Сам шаблон не привязан к
конкретному учебному заведению.

Имя реестра содержит дефис, чтобы оставить пространство имён ``titlepage``
свободным под другие вузовские/факультетские варианты — пользователи смогут
регистрировать ``titlepage-<institution>`` без коллизий.
"""

from __future__ import annotations

from pathlib import Path

from markdown_gost.templates import register, schema_from_yaml

from .preview import render_preview
from .render import render

_HERE = Path(__file__).parent

register(
    "titlepage-university",
    render,
    schema_from_yaml(_HERE / "schema.yaml"),
    preview_fn=render_preview,
)
