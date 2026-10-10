"""Router for Google Workspace wrappers."""
from __future__ import annotations

from . import calendar_tasks, chat, contacts, docs, drive, forms, gmail, keep, meet, sheets, slides, tasks
from .registry import workspace_summary

_RUNNERS = {
    "gmail": gmail.run,
    "mail": gmail.run,
    "drive": drive.run,
    "calendar": calendar_tasks.run,
    "docs": docs.run,
    "sheets": sheets.run,
    "slides": slides.run,
    "forms": forms.run,
    "meet": meet.run,
    "chat": chat.run,
    "contacts": contacts.run,
    "keep": keep.run,
    "tasks": tasks.run,
}


def run_workspace(service: str, task: str = "", args: list[str] | None = None) -> dict | None:
    args = args or []
    normalized = (service or "").strip().lower()
    if normalized in {"catalog", "summary", "registry"}:
        return workspace_summary()
    runner = _RUNNERS.get(normalized)
    if runner is None:
        return {"ok": False, "reason": "unknown_workspace_service", "service": service}
    return runner(task or "list", args)

