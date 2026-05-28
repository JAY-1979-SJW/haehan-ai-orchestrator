"""Re-export stub — real implementation moved to collection/list_collector.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.list_collector import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.list_collector import SomeClass' to still work.
try:
    from .collection.list_collector import *  # noqa: F401,F403
except Exception:
    pass
