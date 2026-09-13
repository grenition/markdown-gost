"""Парсер длинных единиц из конфига в EMU (English Metric Units).

DOCX оперирует EMU: 914400 EMU = 1 inch. python-docx предоставляет
``Length``-обёртки (Cm, Mm, Pt, Inches), но из конфига приходят строки —
здесь они приводятся к int (EMU)."""

from __future__ import annotations

import re

from docx.shared import Cm, Emu, Inches, Length, Mm, Pt

_LENGTH_RE = re.compile(
    r"^\s*(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>cm|mm|pt|in|emu|px)\s*$",
    re.IGNORECASE,
)


def parse_length(value: str) -> Length:
    """Преобразовать строку вида ``"1.25cm"`` / ``"14pt"`` / ``"96px"`` в Length."""

    if not isinstance(value, str):
        raise TypeError(f"length must be str, got {type(value).__name__}")
    match = _LENGTH_RE.match(value)
    if not match:
        raise ValueError(f"invalid length: {value!r}")
    num = float(match.group("value"))
    unit = match.group("unit").lower()
    if unit == "cm":
        return Cm(num)
    if unit == "mm":
        return Mm(num)
    if unit == "pt":
        return Pt(num)
    if unit == "in":
        return Inches(num)
    if unit == "emu":
        return Emu(int(num))
    if unit == "px":
        # Считаем по 96 dpi (Web/CSS-конвенция).
        return Inches(num / 96.0)
    raise ValueError(f"unsupported unit: {unit}")


def parse_pt(value: str) -> float:
    """Получить размер шрифта в пунктах из строки конфига.

    В отличие от :func:`parse_length`, допускает «голое» число без единицы
    измерения и трактует его как pt: ``"10"`` → ``10.0``. Это сделано
    нарочно — пользователи в UI часто вводят размер шрифта одним числом,
    и падать с ``invalid length`` посреди рендера неуместно.
    """

    if isinstance(value, str):
        bare = value.strip()
        try:
            return float(bare)
        except ValueError:
            pass
    length = parse_length(value)
    return length / Pt(1)
