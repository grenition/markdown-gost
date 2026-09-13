"""Make screenshot harness modules importable from unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "screenshot"
if str(SCREENSHOT_DIR) not in sys.path:
    sys.path.insert(0, str(SCREENSHOT_DIR))
