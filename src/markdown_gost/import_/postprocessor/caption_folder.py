"""Fold ``Таблица/Рисунок/Листинг N — Caption`` lines into our directives.

Pandoc emits the caption as a plain paragraph either right before or right
after the captioned block. The postprocessor reattaches it as:

* ``: Caption`` immediately after a GFM table or fenced code block,
* the image's alt-text for ``![alt](url)`` lines.

Up to two blank lines are allowed between the caption and the block in
either direction. Caption numbers are dropped — our exporter regenerates
them. See ``docs/import-syntax-mapping.md`` §2.2.
"""

from __future__ import annotations

import re

from ._common import CODE_FENCE_RE, bump_fallback

STAGE = "caption"

_CAPTION_RE = re.compile(
    r"^(Таблица|Рисунок|Рис\.?|Листинг)\s+\d+(?:\.\d+)*\s*[—\-.:]\s*(\S.*)$",
    re.IGNORECASE,
)
_IMG_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")

_MAX_GAP = 2


def transform(lines: list[str], fallbacks: dict[str, int]) -> list[str]:
    n = len(lines)
    result = list(lines)
    drop = [False] * n
    prepend: dict[int, list[str]] = {}
    protected: set[int] = set()
    fence: str | None = None
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            protected.add(index)
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= len(fence)
                and not match[2].strip()
            ):
                fence = None
        elif match:
            fence = match[1]
            protected.add(index)

    for i in range(n):
        if drop[i] or i in protected:
            continue
        match = _CAPTION_RE.match(result[i].strip())
        if match is None:
            continue
        try:
            kind = _kind_of(match.group(1))
            caption = match.group(2).strip()
            if kind is None:
                continue

            if _try_fold_forward(kind, caption, result, drop, prepend, i):
                continue
            _try_fold_backward(kind, caption, result, drop, prepend, i)
        except Exception:
            bump_fallback(fallbacks, STAGE)

    final: list[str] = []
    for idx in range(n):
        if idx in prepend:
            final.extend(prepend[idx])
        if not drop[idx]:
            final.append(result[idx])
    final.extend(prepend.get(n, []))
    return final


def _kind_of(label: str) -> str | None:
    lowered = label.lower().rstrip(".")
    if lowered == "таблица":
        return "table"
    if lowered in ("рисунок", "рис"):
        return "image"
    if lowered == "листинг":
        return "listing"
    return None


def _try_fold_forward(
    kind: str,
    caption: str,
    result: list[str],
    drop: list[bool],
    prepend: dict[int, list[str]],
    i: int,
) -> bool:
    j = _skip_empties_forward(result, drop, i + 1)
    if j is None:
        return False
    if kind == "table" and _is_table_start(result, j):
        end = j + 1
        while end < len(result) and _TABLE_ROW_RE.match(result[end]):
            end += 1
        drop[i] = True
        for gap in range(i + 1, j):
            drop[gap] = True
        prepend.setdefault(end, []).extend(["", f": {caption}"])
        if end < len(result) and result[end].strip():
            prepend[end].append("")
        return True
    if kind == "listing" and CODE_FENCE_RE.match(result[j]):
        opening = re.match(r"^\s*(`{3,}|~{3,})", result[j])
        assert opening is not None
        close = re.compile(
            r"^\s*" + re.escape(opening[1][0]) + "{" + str(len(opening[1])) + r",}\s*$"
        )
        for end in range(j + 1, len(result)):
            if close.match(result[end]):
                drop[i] = True
                for gap in range(i + 1, j):
                    drop[gap] = True
                prepend.setdefault(end + 1, []).extend(["", f": {caption}"])
                if end + 1 < len(result) and result[end + 1].strip():
                    prepend[end + 1].append("")
                return True
        return False
    if kind == "image":
        img = _IMG_RE.match(result[j])
        if img is not None:
            result[j] = f"![{caption}]({img.group(1)})"
            drop[i] = True
            return True
    return False


def _try_fold_backward(
    kind: str,
    caption: str,
    result: list[str],
    drop: list[bool],
    prepend: dict[int, list[str]],
    i: int,
) -> bool:
    k = _skip_empties_backward(result, drop, i - 1)
    if k is None:
        return False
    if kind == "table" and _TABLE_ROW_RE.match(result[k]):
        result[i] = f": {caption}"
        return True
    if kind == "listing" and CODE_FENCE_RE.match(result[k]):
        listing_start = _listing_block_start(result, k)
        if listing_start is not None:
            result[i] = f": {caption}"
            return True
    if kind == "image":
        img = _IMG_RE.match(result[k])
        if img is not None:
            result[k] = f"![{caption}]({img.group(1)})"
            drop[i] = True
            return True
    return False


def _skip_empties_forward(lines: list[str], drop: list[bool], start: int) -> int | None:
    i = start
    empties = 0
    while i < len(lines) and not drop[i] and lines[i].strip() == "":
        i += 1
        empties += 1
    if i >= len(lines) or drop[i] or empties > _MAX_GAP:
        return None
    return i


def _skip_empties_backward(lines: list[str], drop: list[bool], start: int) -> int | None:
    i = start
    empties = 0
    while i >= 0 and not drop[i] and lines[i].strip() == "":
        i -= 1
        empties += 1
    if i < 0 or drop[i] or empties > _MAX_GAP:
        return None
    return i


def _is_table_start(lines: list[str], idx: int) -> bool:
    if not _TABLE_ROW_RE.match(lines[idx]):
        return False
    nxt = idx + 1
    if nxt >= len(lines):
        return False
    return bool(_TABLE_ROW_RE.match(lines[nxt]))


def _table_block_start(lines: list[str], idx: int) -> int:
    while idx > 0 and _TABLE_ROW_RE.match(lines[idx - 1]):
        idx -= 1
    return idx


def _listing_block_start(lines: list[str], closing_idx: int) -> int | None:
    i = closing_idx - 1
    while i >= 0 and not CODE_FENCE_RE.match(lines[i]):
        i -= 1
    return i if i >= 0 else None


__all__ = ["STAGE", "transform"]
