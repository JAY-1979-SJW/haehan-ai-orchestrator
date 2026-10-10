"""탐색 서비스 라우터"""
from __future__ import annotations

from . import run as _explorer_run
from scripts.common.gate import check as gate_check

__status__ = {
    "tasks": {
        "page (페이지 구조 스냅샷)": "done",
        "tabs (탭 인터페이스 탐색)": "done",
    },
    "note": "page_snapshot + tab_explorer 완성. 비파괴 읽기전용",
}


def run_explorer(task: str, sub: str, args: list[str]) -> None:
    """탐색 서비스 라우팅.

    task: page | tabs
    """
    gate_check("goto")
    _explorer_run(task or "page", args)
