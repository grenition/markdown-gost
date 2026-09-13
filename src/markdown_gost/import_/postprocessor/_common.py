"""Shared helpers for the postprocessor transformers."""

from __future__ import annotations

import re

CODE_FENCE_RE = re.compile(r"^\s*```")


def bump_fallback(fallbacks: dict[str, int], stage: str) -> None:
    """Record a fallback in both the in-memory counter and the Prometheus metric."""
    from ..metrics import IMPORT_FALLBACK_TOTAL

    fallbacks[stage] = fallbacks.get(stage, 0) + 1
    IMPORT_FALLBACK_TOTAL.labels(stage=stage).inc()


__all__ = ["CODE_FENCE_RE", "bump_fallback"]
