"""Workspace Keep catalog-only wrapper."""
from __future__ import annotations

from .registry import get_surface


def run(task: str = "open", args: list[str] | None = None) -> dict:
    return {"ok": False, "service": "keep", "task": task or "open", "mode": "catalog_only", "surface": get_surface("keep")}

