"""Compatibility wrapper for the archived one-off script."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.archive.one_off.validate_site_policy_config import *  # noqa: F401,F403


if __name__ == "__main__":
    from scripts.archive.one_off.validate_site_policy_config import main

    main()
