"""Optional prometheus_client support.

The library core must stay importable without prometheus_client installed
(pip-only users do not need it — only long-running services scrape metrics).
When the package is missing, metric objects degrade to no-op stand-ins with
the same interface used across this codebase (``labels``/``inc``/``observe``).
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext

try:
    from prometheus_client import Counter, Histogram
except ModuleNotFoundError:  # pragma: no cover - exercised only without the extra

    class _NoopMetric:
        """Structural stand-in for Counter/Histogram."""

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def labels(self, *_args: object, **_kwargs: object) -> _NoopMetric:
            return self

        def inc(self, *_args: object, **_kwargs: object) -> None:
            return None

        def observe(self, *_args: object, **_kwargs: object) -> None:
            return None

        def time(self) -> AbstractContextManager[None]:
            return nullcontext(None)

    Counter = _NoopMetric  # type: ignore[assignment,misc]
    Histogram = _NoopMetric  # type: ignore[assignment,misc]

__all__ = ["Counter", "Histogram"]
