"""cafe_mixin 공통 헬퍼 (공유 leaf).

서브믹스인들이 공유하는 _js 로더 등. [docs/module_separation_standard.md]
"""

from __future__ import annotations


def _js(name: str) -> str:
    from pathlib import Path as _Path

    return (_Path(__file__).parent.parent / "_js" / name).read_text(encoding="utf-8")
