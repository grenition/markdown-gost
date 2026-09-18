"""Regenerate the HTML calibration reference from a fresh --report-only run.

Usage:
    python tests/screenshot/html_calibration.py --report-only
    python tests/screenshot/update_html_calibration_reference.py [--yes]

Refreshes ``captured_on``, ``aggregate`` and per-case metrics in
``html-calibration-reference.json`` from the summary written by the latest
``--report-only`` run. Schema, thresholds, oracle and browser notes are
preserved; per-case entries keep any extra reference-only fields. Only for
deliberate, reviewed rendering changes (AGENTS.md Rule 6) — never to make
an unexplained diff disappear. Prints old→new deltas; ``--yes`` applies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
REFERENCE = ROOT / "html-calibration-reference.json"
SUMMARY = ROOT / "_artifacts" / "html-calibration" / "summary.json"


def _merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old)
    merged.update(new)
    return merged


def main() -> int:
    args = _parse_args()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("errors"):
        print("summary contains calibration errors; fix them first:")
        for error in summary["errors"]:
            print(f"  - {error['case']}: {error['error']}")
        return 2

    old_cases = {case["case"]: case for case in reference.get("cases", [])}
    new_cases = {case["case"]: case for case in summary.get("cases", [])}
    added = sorted(new_cases.keys() - old_cases.keys())
    removed = sorted(old_cases.keys() - new_cases.keys())
    if removed:
        print(f"cases disappeared from summary: {removed}; refusing")
        return 2

    print("old -> new differing_rate:")
    for name in sorted(new_cases):
        old_rate = old_cases.get(name, {}).get("differing_rate")
        new_rate = new_cases[name].get("differing_rate")
        marker = " (new)" if name in added else ""
        print(f"  {name:<34} {old_rate!s:>10} -> {new_rate!s:>10}{marker}")
    old_agg = reference.get("aggregate", {}).get("differing_rate")
    print(f"  {'aggregate':<34} {old_agg!s:>10} -> {summary['aggregate']['differing_rate']!s:>10}")
    if not args.yes:
        print("\ndry run; re-run with --yes to write the reference")
        return 0

    reference["captured_on"] = dt.date.today().isoformat()
    reference["aggregate"] = _merge(reference.get("aggregate", {}), summary["aggregate"])
    reference["cases"] = [
        _merge(old_cases.get(name, {}), new_cases[name])
        for name in sorted(new_cases)
    ]
    REFERENCE.write_text(
        json.dumps(reference, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {REFERENCE}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="apply (default: dry run)")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
