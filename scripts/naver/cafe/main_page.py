"""Re-export stub — real implementation moved to background/main_page.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

import contextlib

from .background.main_page import *  # noqa: F403

# Allow 'from scripts.naver.cafe.main_page import SomeClass' to still work.
# 하위 세부 모듈을 재노출하는 호환 shim - `from .xxx import *` 실패 시 조용히 무시, 실제 실행 로직 없음, 부작용 없음
with contextlib.suppress(Exception):
    from .background.main_page import *  # noqa: F403
