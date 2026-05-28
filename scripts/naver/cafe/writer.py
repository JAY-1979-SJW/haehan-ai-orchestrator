"""Re-export stub — real implementation moved to write/writer.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .write.writer import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.writer import SomeClass' to still work.
try:
    from .write.writer import *  # noqa: F401,F403
except Exception:
    pass
