"""Re-export stub — real implementation moved to collection/topic_search.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

from .collection.topic_search import *  # noqa: F403

# Allow 'from scripts.naver.cafe.topic_search import SomeClass' to still work.
try:
    from .collection.topic_search import *  # noqa: F403
except Exception:  # noqa: BLE001 - 하위 세부 모듈을 재노출하는 호환 shim - `from .xxx import *` 실패 시 조용히 무시(pass), 실제 실행 로직 없음, 부작용 없음
    pass
