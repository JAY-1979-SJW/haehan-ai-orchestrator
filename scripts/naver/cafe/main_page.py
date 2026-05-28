"""Re-export stub — real implementation moved to background/main_page.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .background.main_page import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.main_page import SomeClass' to still work.
try:
    from .background.main_page import *  # noqa: F401,F403
except Exception:
    pass
