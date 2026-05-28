"""Re-export stub — real implementation moved to analysis/classifier.py.

This file is kept for backward compatibility.
"""
from __future__ import annotations
from .analysis.classifier import *  # noqa: F401,F403

# Allow 'from scripts.naver.cafe.classifier import SomeClass' to still work.
try:
    from .analysis.classifier import *  # noqa: F401,F403
except Exception:
    pass
