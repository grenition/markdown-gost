"""Mark well-known service headings with ``{.unnumbered}``.

In ГОСТ-formatted theses СОДЕРЖАНИЕ / ВВЕДЕНИЕ / ЗАКЛЮЧЕНИЕ / СПИСОК
ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ are conventionally rendered without a chapter
number even though they sit at heading-level 1. Our exporter relies on the
``.unnumbered`` role (``docs/syntax.md``).
"""

from __future__ import annotations

import re

from ._common import CODE_FENCE_RE, bump_fallback

STAGE = "unnumbered_heading"

# Configurable in-code list (not YAML) per the task spec.
_KNOWN_UNNUMBERED = frozenset(
    {
        "содержание",
        "введение",
        "заключение",
        "список использованных источников",
    }
)

_H1_RE = re.compile(r"^(#)\s+(\S.*)$")


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
            match = _H1_RE.match(line)
            if match is None:
                out.append(line)
                continue
            text = match.group(2).strip()
            if text.lower() in _KNOWN_UNNUMBERED:
                out.append(f"# {text} {{.unnumbered}}")
            else:
                out.append(line)
        except Exception:
            bump_fallback(fallbacks, STAGE)
            out.append(line)
    return out


__all__ = ["STAGE", "transform"]
