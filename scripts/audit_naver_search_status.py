"""Compatibility entrypoint for the Naver search operational audit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.archive.debug.audit_naver_search_status import audit, main  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
