"""Re-export stub — real implementation moved to analysis/organizer.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .analysis.organizer import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.organizer import SomeClass' to still work.
try:
    from .analysis.organizer import *  # noqa: F401,F403
except Exception:
    pass
