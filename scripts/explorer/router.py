"""탐색 서비스 라우터"""
from __future__ import annotations

from . import run as _explorer_run
from scripts.gate import check as gate_check


def run_explorer(task: str, sub: str, args: list[str]) -> None:
    """탐색 서비스 라우팅.

    task: page | tabs
    """
    gate_check("goto")
    _explorer_run(task or "page", args)
