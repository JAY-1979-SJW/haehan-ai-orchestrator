"""Re-export stub — real implementation moved to collection/member_collect.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.member_collect import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.member_collect import SomeClass' to still work.
try:
    from .collection.member_collect import *  # noqa: F401,F403
except Exception:
    pass
