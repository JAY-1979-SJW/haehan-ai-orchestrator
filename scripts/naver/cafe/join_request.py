"""Re-export stub — real implementation moved to write/join_request.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .write.join_request import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.join_request import SomeClass' to still work.
try:
    from .write.join_request import *  # noqa: F401,F403
except Exception:
    pass
