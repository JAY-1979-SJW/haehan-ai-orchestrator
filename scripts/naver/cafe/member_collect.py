"""Re-export stub — real implementation moved to collection/member_collect.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

import contextlib

from .collection.member_collect import *  # noqa: F403

# Allow 'from scripts.naver.cafe.member_collect import SomeClass' to still work.
# 하위 세부 모듈을 재노출하는 호환 shim - import 실패 시 조용히 무시, 실제 실행 로직 없음, 부작용 없음
with contextlib.suppress(Exception):
    from .collection.member_collect import *  # noqa: F403
