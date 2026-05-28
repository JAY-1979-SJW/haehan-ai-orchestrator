"""Re-export stub — real implementation moved to collection/topic_search.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .collection.topic_search import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.topic_search import SomeClass' to still work.
try:
    from .collection.topic_search import *  # noqa: F401,F403
except Exception:
    pass
