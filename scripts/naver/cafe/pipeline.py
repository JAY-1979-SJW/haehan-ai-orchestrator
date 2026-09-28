"""Re-export stub — real implementation moved to analysis/pipeline.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

from contextlib import suppress

from .analysis.pipeline import *  # noqa: F403

# Allow 'from scripts.naver.cafe.pipeline import SomeClass' to still work.
with suppress(Exception):
    from .analysis.pipeline import *  # noqa: F403
