"""Workspace Calendar wrapper preserving the existing top-level implementation."""
from __future__ import annotations

from scripts.google.common import calendar_tasks as _legacy


def run(task: str = "today", args: list[str] | None = None) -> None:
    return _legacy.run(task or "today", args or [])

