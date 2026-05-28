"""Re-export stub — real implementation moved to collection/explorer.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.explorer import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.explorer import SomeClass' to still work.
try:
    from .collection.explorer import *  # noqa: F401,F403
except Exception:
    pass
