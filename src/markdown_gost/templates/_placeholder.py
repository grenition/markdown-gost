"""Красный плейсхолдер для случаев, когда шаблон не найден или невалидны параметры.

Используется реестром (``render_template``) и ``RenderableFactory`` —
никогда не должен «уронить» весь рендер: лучше видимый маркер, чем тихая
потеря содержимого.
"""

from __future__ import annotations

import logging
from typing import Any

from docx.shared import RGBColor

from markdown_gost.config.schema import Config
from markdown_gost.core.ast import nodes as ast
from markdown_gost.renderable.paragraph import Paragraph

_log = logging.getLogger(__name__)


def make_placeholder(
    parent: Any,
    config: Config,
    *,
    template_name: str,
    reason: str,
) -> Paragraph:
    """Собрать абзац с красным предупреждением о проблеме шаблона."""

    _log.warning(
        "template %r could not be rendered: %s", template_name, reason
    )
    paragraph = Paragraph(parent, config)
    paragraph.add_inline_nodes(
        [ast.Text(text=f"[template '{template_name}' error: {reason}]")]
    )
    for run in paragraph.docx_paragraph.runs:
        run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
        run.font.bold = True
    return paragraph
