"""Workspace Drive wrapper preserving the existing top-level implementation."""
from __future__ import annotations

from scripts.google.common import drive as _legacy


def run(task: str = "list", args: list[str] | None = None) -> None:
    return _legacy.run(task or "list", args or [])

