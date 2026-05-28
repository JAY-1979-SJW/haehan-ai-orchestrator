"""Re-export stub — real implementation moved to collection/cafe_explorer.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.cafe_explorer import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.cafe_explorer import SomeClass' to still work.
try:
    from .collection.cafe_explorer import *  # noqa: F401,F403
except Exception:
    pass
