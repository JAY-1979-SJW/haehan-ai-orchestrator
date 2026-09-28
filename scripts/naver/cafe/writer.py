"""Re-export stub — real implementation moved to write/writer.py.

This file is kept for backward compatibility.
"""

from __future__ import annotations

from .write.writer import *  # noqa: F403

# Allow 'from scripts.naver.cafe.writer import SomeClass' to still work.
try:
    from .write.writer import *  # noqa: F403
except Exception:  # noqa: BLE001 - 하위 세부 모듈을 재노출하는 호환 shim - `from .xxx import *` 실패 시 조용히 무시(pass), 실제 실행 로직 없음, 부작용 없음
    pass
