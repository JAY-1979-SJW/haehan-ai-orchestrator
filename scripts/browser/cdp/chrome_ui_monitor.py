"""Compatibility entrypoint for the archived Chrome UI monitor."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.archive.misc.chrome_ui_monitor import run_monitor  # noqa: E402

if __name__ == "__main__":
    poll_interval = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    run_monitor(poll_interval_s=poll_interval)
