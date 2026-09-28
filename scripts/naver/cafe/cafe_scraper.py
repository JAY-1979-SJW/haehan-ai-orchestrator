"""Re-export stub — real implementation moved to collection/cafe_scraper.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

from contextlib import suppress

from .collection.cafe_scraper import *  # noqa: F403

# Allow 'from scripts.naver.cafe.cafe_scraper import SomeClass' to still work.
with suppress(Exception):
    from .collection.cafe_scraper import *  # noqa: F403
