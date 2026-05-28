"""Re-export stub — real implementation moved to collection/collector.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.collector import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.collector import SomeClass' to still work.
try:
    from .collection.collector import *  # noqa: F401,F403
except Exception:
    pass
