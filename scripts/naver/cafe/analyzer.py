"""Re-export stub — real implementation moved to analysis/analyzer.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .analysis.analyzer import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.analyzer import SomeClass' to still work.
try:
    from .analysis.analyzer import *  # noqa: F401,F403
except Exception:
    pass
