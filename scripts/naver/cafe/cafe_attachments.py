"""Re-export stub — real implementation moved to collection/cafe_attachments.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.cafe_attachments import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.cafe_attachments import SomeClass' to still work.
try:
    from .collection.cafe_attachments import *  # noqa: F401,F403
except Exception:
    pass
