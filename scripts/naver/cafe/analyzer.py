"""Re-export stub — real implementation moved to analysis/analyzer.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

from contextlib import suppress

from .analysis.analyzer import *  # noqa: F403

# Allow 'from scripts.naver.cafe.analyzer import SomeClass' to still work.
with suppress(Exception):
    from .analysis.analyzer import *  # noqa: F403
