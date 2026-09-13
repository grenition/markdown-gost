"""Prometheus metrics for the import pipeline (ADR-0006, T032).

Metric names mirror the conversion-side metrics so dashboards stay symmetric.
``format`` is one of ``docx``/``pdf``; ``result`` is ``ok``/``error``;
``stage`` identifies the postprocessor step that fell back to raw output
(used from T033 onwards).
"""

from __future__ import annotations

from markdown_gost.metrics_compat import Counter, Histogram

IMPORT_TOTAL = Counter(
    "md2gost_import_total",
    "Total import runs per source format and outcome.",
    labelnames=("format", "result"),
)

IMPORT_DURATION = Histogram(
    "md2gost_import_duration_seconds",
    "End-to-end import wall time per source format.",
    labelnames=("format",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

IMPORT_FALLBACK_TOTAL = Counter(
    "md2gost_import_fallback_total",
    "Postprocessor blocks that fell back to raw pandoc output, by stage.",
    labelnames=("stage",),
)

__all__ = [
    "IMPORT_DURATION",
    "IMPORT_FALLBACK_TOTAL",
    "IMPORT_TOTAL",
]
