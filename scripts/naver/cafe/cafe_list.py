"""Re-export stub — real implementation moved to collection/cafe_list.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.cafe_list import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.cafe_list import SomeClass' to still work.
try:
    from .collection.cafe_list import *  # noqa: F401,F403
except Exception:
    pass
