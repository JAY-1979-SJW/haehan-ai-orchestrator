"""Workspace Docs wrapper preserving the existing top-level implementation."""
from __future__ import annotations

from scripts.google.common import docs as _legacy


def run(task: str = "recent", args: list[str] | None = None) -> None:
    return _legacy.run(task or "recent", args or [])

