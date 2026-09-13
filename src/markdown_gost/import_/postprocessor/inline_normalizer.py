"""Translate pandoc bracketed spans to our inline syntax.

* ``[text]{.underline}`` → canonical underline span
* ``[text]{.smallcaps}``, ``[text]{.mark}``, … → bare ``text``

See ``docs/import-syntax-mapping.md`` §2.4. Other inline pandoc constructs
(``**bold**``, ``*italic*``, ``~~strike~~``, backtick code) are already in
our syntax and are passed through untouched.
"""

from __future__ import annotations

import re

from ._common import CODE_FENCE_RE, bump_fallback

STAGE = "inline"

_SPAN_RE = re.compile(r"\[([^\]\n]+)\]\{([^}\n]*)\}")


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
            out.append(_SPAN_RE.sub(_replace_span, line))
        except Exception:
            bump_fallback(fallbacks, STAGE)
            out.append(line)
    return out


def _replace_span(match: re.Match[str]) -> str:
    text = match.group(1)
    attrs = match.group(2)
    classes = {tok[1:] for tok in attrs.split() if tok.startswith(".")}
    if "underline" in classes:
        return f"[{text}]{{.underline}}"
    return text


__all__ = ["STAGE", "transform"]
