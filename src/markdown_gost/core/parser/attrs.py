"""Парсер pandoc-style блоков атрибутов ``{key=value ...}``.

Используется для картинок (T012); в дальнейшем — для таблиц/листингов.

Текущий публичный API ограничен размерами (``width``/``height``) — это всё,
что нужно T012. По мере добавления новых атрибутов сюда будут приходить
дополнительные функции/классы.
"""

from __future__ import annotations

import re
import shlex

__all__ = [
    "ATTR_BLOCK_RE",
    "Size",
    "parse_image_attrs",
    "parse_quoted_attrs",
    "parse_size_list",
    "parse_size_value",
    "split_caption_attrs_block",
]


_VALID_UNITS = ("%", "cm", "mm", "pt", "px", "in")

ATTR_BLOCK_RE = re.compile(r"\{([^}\n]+)\}")
_KV_RE = re.compile(
    r"(?P<key>[A-Za-z_][\w-]*)\s*=\s*"
    r"(?P<val>auto|\d+(?:\.\d+)?(?:%|cm|mm|pt|px|in))",
    flags=re.IGNORECASE,
)
_NUMBER_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)(%|cm|mm|pt|px|in)$", flags=re.IGNORECASE)


Size = tuple[float, str]


def parse_attributes(raw: str) -> dict[str, str]:
    """Parse the single attribute grammar defined in syntax.md."""
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]
    values: dict[str, str] = {}
    for token in shlex.split(raw):
        if token.startswith("#"):
            key, value = "id", token[1:]
        elif token.startswith("."):
            key, value = token, "true"
        elif "=" in token:
            key, value = token.split("=", 1)
        else:
            raise ValueError(f"invalid attribute: {token!r}")
        name = key[1:] if key.startswith(".") else key
        if not re.fullmatch(r"[^\W\d][\w-]*", name, re.UNICODE):
            raise ValueError(f"invalid attribute name: {key!r}")
        if key == "id" and not re.fullmatch(r"[^\W\d][\w-]*", value, re.UNICODE):
            raise ValueError(f"invalid identifier: {value!r}")
        if key in values:
            raise ValueError(f"duplicate attribute: {key}")
        values[key] = value
    return values


def split_attributes(raw: str) -> tuple[str, dict[str, str]]:
    match = re.search(r"(?<!\\)\{([^{}\n]+)\}\s*$", raw)
    if match is None:
        return raw.rstrip(), {}
    return raw[: match.start()].rstrip(), parse_attributes(match.group(1))


def parse_size_value(value: str) -> Size | None:
    """Распарсить ``"80%"`` / ``"10cm"`` / ``"auto"`` → ``(value, unit)``.

    Возвращает None для невалидных значений. ``"auto"`` → ``(0.0, "auto")``.
    """

    if not isinstance(value, str):
        return None
    val = value.strip().lower()
    if val == "auto":
        return (0.0, "auto")
    m = _NUMBER_UNIT_RE.match(val)
    if not m:
        return None
    return (float(m.group(1)), m.group(2).lower())


def parse_image_attrs(raw: str) -> tuple[Size | None, Size | None]:
    """Распарсить ``{width=80% height=auto}`` → ``(width, height)``.

    Принимает либо текст с фигурными скобками, либо без них.
    Невалидные пары игнорируются. Возвращает ``(None, None)``, если ничего не нашли.
    """

    width: Size | None = None
    height: Size | None = None
    block_match = ATTR_BLOCK_RE.match(raw.strip())
    inner = block_match.group(1) if block_match else raw
    for m in _KV_RE.finditer(inner):
        key = m.group("key").lower()
        parsed = parse_size_value(m.group("val"))
        if parsed is None:
            continue
        if key == "width":
            width = parsed
        elif key == "height":
            height = parsed
    return width, height


def is_supported_unit(unit: str) -> bool:
    """Проверка единицы измерения. ``auto`` — спецзначение, не относящееся к set."""

    return unit.lower() in _VALID_UNITS


# ---- caption / table attrs (quoted "key=\"value\"" syntax) ----------------

_QUOTED_KV_RE = re.compile(
    r'(?P<key>[A-Za-z_][\w-]*)\s*=\s*"(?P<val>[^"\n]*)"',
    flags=re.IGNORECASE,
)
_TRAILING_ATTR_BLOCK_RE = re.compile(r"\s*\{(?P<inner>[^}\n]*)\}\s*$")


def parse_quoted_attrs(raw: str) -> dict[str, str]:
    """Распарсить ``key="value" key2="value2"`` → ``{key: value, ...}``.

    Принимает либо текст с фигурными скобками, либо без них. Невалидные пары
    пропускаются. Используется для атрибутов таблиц, где значение может
    содержать запятые (например, ``widths="20%, 30%, 50%"``).
    """

    block_match = ATTR_BLOCK_RE.match(raw.strip())
    inner = block_match.group(1) if block_match else raw
    return {m.group("key").lower(): m.group("val").strip() for m in _QUOTED_KV_RE.finditer(inner)}


def split_caption_attrs_block(raw: str) -> tuple[str, dict[str, str]]:
    """Отделить от текста подписи хвостовой блок ``{key="..." ...}``.

    Возвращает ``(text, attrs)``. Если блок отсутствует — ``attrs`` пустой,
    ``text`` совпадает с исходником (без trailing-whitespace).
    """

    if not raw:
        return raw, {}
    m = _TRAILING_ATTR_BLOCK_RE.search(raw)
    if m is None:
        return raw.rstrip(), {}
    text = raw[: m.start()].rstrip()
    attrs = parse_quoted_attrs(m.group("inner"))
    return text, attrs


def parse_size_list(
    raw: str,
    *,
    expected_count: int,
    allow_percent: bool,
    field_name: str = "size",
) -> list[Size]:
    """Распарсить ``"20%, 30%, auto"`` → список ``(value, unit)``.

    Поднимает :class:`ValueError`, если число элементов не совпадает с
    ``expected_count`` или среди значений есть невалидные/недопустимые
    (например, ``%`` при ``allow_percent=False``).
    """

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) != expected_count:
        raise ValueError(
            f"{field_name}: expected {expected_count} values, got {len(parts)} ({raw!r})"
        )
    out: list[Size] = []
    for idx, part in enumerate(parts, start=1):
        size = parse_size_value(part)
        if size is None:
            raise ValueError(
                f"{field_name}[{idx}]: invalid size value {part!r} "
                f"(expected one of: %, cm, mm, pt, in, px, auto)"
            )
        if size[1] == "%" and not allow_percent:
            raise ValueError(
                f"{field_name}[{idx}]: percent values are not allowed in this context "
                f"(got {part!r})"
            )
        out.append(size)
    return out
