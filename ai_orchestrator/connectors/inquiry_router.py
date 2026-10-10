"""문의 게시판 (/api/v1/inquiries).

- POST  : 공개(비로그인) 접수 — 허니팟·레이트리밋·길이제한으로 스팸 차단, 새 문의 텔레그램 알림.
- GET   : owner/admin 목록 조회.
- PATCH : owner/admin 상태/메모 갱신.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from tools.gates.auth import require_role

from ..audit.audit_logger import log_event

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]

inquiry_router = APIRouter(prefix="/inquiries", tags=["inquiry"])

# ── 레이트리밋 (IP당 시간 제한, in-memory) ──────────────────────────────────
_RL: dict[str, list[float]] = {}
_RL_WINDOW = 3600
_RL_MAX = 5


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


class InquiryCreate(BaseModel):
    name: str
    contact: str = ""
    company: str = ""
    subject: str = ""
    message: str
    website: str = ""  # 허니팟(봇이 채우면 스팸으로 간주)


class InquiryUpdate(BaseModel):
    status: str | None = None
    memo: str | None = None


@inquiry_router.post("")
def create_inquiry(body: InquiryCreate, request: Request) -> dict:
    """공개 문의 접수."""
    # 허니팟: 채워져 있으면 스팸 → 조용히 접수한 척
    if (body.website or "").strip():
        return {"ok": True}

    # 레이트리밋
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    times = [t for t in _RL.get(ip, []) if now - t < _RL_WINDOW]
    if len(times) >= _RL_MAX:
        raise HTTPException(status_code=429, detail="문의가 너무 많습니다. 잠시 후 다시 시도해주세요.")
    times.append(now)
    _RL[ip] = times

    _ensure_path()
    from scripts.inquiry.store import add_inquiry

    try:
        rec = add_inquiry(body.model_dump())
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve

    # 새 문의 텔레그램 알림 (설정된 경우 best-effort)
    try:
        from scripts.community.notifier import send_message

        send_message(
            "📩 새 문의가 접수되었습니다\n"
            f"이름: {rec['name']}\n"
            f"연락처: {rec['contact'] or '-'}\n"
            f"회사: {rec['company'] or '-'}\n"
            f"제목: {rec['subject']}\n"
            f"내용: {rec['message'][:300]}"
        )
    except Exception as exc:  # noqa: BLE001 — 알림 실패해도 접수는 성공 처리
        logger.warning("문의 접수 알림 발송 실패: %s", type(exc).__name__)
        pass

    log_event(
        "INQUIRY_CREATE",
        task_id="-",
        actor=rec["name"][:20],
        role="public",
        decision="ok",
        note=f"id={rec['id']} subj={rec['subject'][:20]}",
    )
    return {"ok": True, "id": rec["id"]}


@inquiry_router.get("")
def list_inquiries(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """문의 목록(최근 우선) — 관리자 전용."""
    _ensure_path()
    from scripts.inquiry.store import counts
    from scripts.inquiry.store import list_inquiries as _ls

    return {"ok": True, "items": _ls(), "counts": counts()}


@inquiry_router.patch("/{inquiry_id}")
def update_inquiry(inquiry_id: str, body: InquiryUpdate, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """상태/메모 갱신 — 관리자 전용."""
    _ensure_path()
    from scripts.inquiry.store import update_inquiry as _up

    ok = _up(inquiry_id, status=body.status, memo=body.memo)
    if not ok:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다")
    log_event(
        "INQUIRY_UPDATE",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"id={inquiry_id} status={body.status}",
    )
    return {"ok": True}
