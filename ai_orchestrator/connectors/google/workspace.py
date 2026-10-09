"""Google Workspace 라우트 — Gmail·Drive·Calendar·Docs 요약."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends

from tools.gates.auth import require_role

from ._helpers import audit, duration_ms

router = APIRouter()


@router.get("/catalog")
def get_workspace_catalog(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Google Workspace 서비스 카탈로그 반환."""
    t0 = time.monotonic()
    from scripts.google.workspace.registry import workspace_summary

    summary = workspace_summary()
    audit("GOOGLE_WORKSPACE_CATALOG_READ", user, status="ok")
    return {**summary, "duration_ms": duration_ms(t0)}


@router.get("/gmail/inbox")
def get_gmail_inbox(
    max_results: int = 20,
    hours: int = 48,
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Gmail 수신함 조회."""
    t0 = time.monotonic()
    try:
        from ai_orchestrator.connectors.google.gmail_reader import fetch_recent_emails

        items = fetch_recent_emails(max_results=max_results, hours=hours)
        audit("GOOGLE_GMAIL_INBOX_READ", user, status="ok", note=f"count={len(items)}")
        return {"ok": True, "items": items, "count": len(items), "duration_ms": duration_ms(t0)}
    except Exception as e:  # noqa: BLE001 - Gmail 받은편지함 조회 API — 예외 시 {ok: False, error}로 반환, 읽기 전용 조회 실패 처리
        return {"ok": False, "error": str(e)[:200], "duration_ms": duration_ms(t0)}


@router.get("/drive/status")
def get_drive_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Google Drive 연동 상태."""
    t0 = time.monotonic()
    audit("GOOGLE_DRIVE_STATUS_READ", user, status="ok")
    return {
        "ok": True,
        "status": "catalog_only",
        "note": "Drive automation via CDP browser session",
        "duration_ms": duration_ms(t0),
    }


@router.get("/calendar/status")
def get_calendar_status(
    user: dict = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Google Calendar 연동 상태."""
    t0 = time.monotonic()
    audit("GOOGLE_CALENDAR_STATUS_READ", user, status="ok")
    return {
        "ok": True,
        "status": "catalog_only",
        "note": "Calendar automation via CDP browser session",
        "duration_ms": duration_ms(t0),
    }
