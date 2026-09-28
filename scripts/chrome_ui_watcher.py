"""Compatibility wrapper for the archived Chrome UI watcher."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.archive.misc.chrome_ui_watcher import *  # noqa: E402,F403
