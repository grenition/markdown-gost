"""Strip manual leading numbering (``1``, ``1.2``, ``2.3.4`` …) from headings.

Our exporter generates heading numbers itself, so any numbering left in the
source would be doubled on re-export. See
``docs/import-syntax-mapping.md`` §2.1.
"""

from __future__ import annotations

import re

from ._common import CODE_FENCE_RE, bump_fallback

STAGE = "heading"

_HEADING_RE = re.compile(r"^(#{1,6})\s+\d+(?:\.\d+)*\s+(\S.*)$")


def transform(lines: list[str], fallbacks: dict[str, int]) -> list[str]:
    out: list[str] = []
    in_code = False
    for line in lines:
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        try:
            match = _HEADING_RE.match(line)
            out.append(f"{match.group(1)} {match.group(2)}" if match else line)
        except Exception:
            bump_fallback(fallbacks, STAGE)
            out.append(line)
    return out


__all__ = ["STAGE", "transform"]
