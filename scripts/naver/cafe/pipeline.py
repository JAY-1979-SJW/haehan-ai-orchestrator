"""Re-export stub — real implementation moved to analysis/pipeline.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .analysis.pipeline import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.pipeline import SomeClass' to still work.
try:
    from .analysis.pipeline import *  # noqa: F401,F403
except Exception:
    pass
