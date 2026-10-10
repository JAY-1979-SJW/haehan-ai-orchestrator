"""리뷰·문의 엔드포인트."""

from __future__ import annotations

import sys
import time as _t

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role
from tools.gates.send_approval import require_send_approval

from ...audit.audit_logger import log_event
from ._helpers import ROOT, elapsed_ms, load_ss, now_iso, run_with_cdp_page, save_ss

router = APIRouter()


@router.get("/reviews")
def api_reviews(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    log_event("SMARTSTORE_REVIEWS_READ", task_id="-", actor=user["actor"], role=user["role"], decision="ok", note="")
    return load_ss("reviews")


@router.post("/reviews/collect")
def api_reviews_collect(limit: int = 30, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    sys.path.insert(0, str(ROOT))
    t0 = _t.monotonic()
    try:
        from scripts.naver.smartstore import NaverSmartStore

        result = run_with_cdp_page(lambda page: NaverSmartStore(page).list_reviews(limit=limit))
    except Exception as e:  # noqa: BLE001 - 리뷰 조회/자동답변 엔드포인트 — reply 엔드포인트는 body.confirm 검증이 try 블록 이전에 끝난 뒤에만 실제 저장하며, except는 CDP 실패를 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e)}
    result.update({"collected_at": now_iso(), "duration_ms": elapsed_ms(t0)})
    save_ss("reviews", result)
    log_event(
        "SMARTSTORE_REVIEWS_COLLECT",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result


# ── 미답변 리뷰 조회·답변 (구 chat.py _run_tool 대체, 비-AI 답변 초안 생성) ──────────


@router.get("/reviews/pending")
def api_reviews_pending(limit: int = 20, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """미답변 리뷰 목록 조회 + 답변 초안 생성(review_reply.py 재사용, 유료 AI 미사용)."""
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder

    def _fetch_pending(page):
        result = ReviewAutoResponder(page).get_pending(limit=limit)
        if result.get("ok") and result.get("pending"):
            result["pending"] = ReviewAutoResponder(None).generate_replies(result["pending"])
        return result

    try:
        result = run_with_cdp_page(_fetch_pending)
    except Exception as e:  # noqa: BLE001 - 리뷰 조회/자동답변 엔드포인트 — reply 엔드포인트는 body.confirm 검증이 try 블록 이전에 끝난 뒤에만 실제 저장하며, except는 CDP 실패를 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_REVIEWS_PENDING",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note="",
    )
    return result


class ReplyReviewsRequest(BaseModel):
    limit: int = 10
    dry_run: bool = True
    confirm: bool = False
    # 실제 저장(dry_run=false)일 때 사용자가 직접 입력한 승인 문구. 없거나 다르면 403.
    send_confirm: str | None = None


@router.post("/reviews/reply")
def api_reviews_reply(body: ReplyReviewsRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """미답변 리뷰에 자동 답변 저장 (쓰기). confirm=true 없이는 거부, dry_run 기본 True."""
    if not body.confirm:
        return {"ok": False, "error": "confirm=true 없이는 실행할 수 없습니다."}
    if body.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "note": "dry_run=True — 실제 저장 없이 계획만 반환합니다.",
            "limit": body.limit,
        }
    from tools.gates.gate_core import CONFIRM_TEXTS

    # 실제 저장은 사용자가 직접 입력한 승인 문구가 있어야 한다(없으면 403, CDP 접근 전에 차단)
    require_send_approval("smartstore_reply", send_confirm=body.send_confirm, expected=CONFIRM_TEXTS["smartstore_reply"])
    sys.path.insert(0, str(ROOT))
    from scripts.naver.smartstore.product.review_reply import ReviewAutoResponder

    try:
        result = run_with_cdp_page(
            lambda page: ReviewAutoResponder(page).reply_pending(limit=body.limit, confirmed=True)
        )
    except Exception as e:  # noqa: BLE001 - 리뷰 조회/자동답변 엔드포인트 — reply 엔드포인트는 body.confirm 검증이 try 블록 이전에 끝난 뒤에만 실제 저장하며, except는 CDP 실패를 {ok: False, error, hint}로 반환할 뿐 confirm 검증을 우회하지 않음.
        result = {"ok": False, "error": str(e), "hint": "CDP 브라우저가 실행 중인지 확인하세요"}
    log_event(
        "SMARTSTORE_REVIEWS_REPLY",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok" if result.get("ok") else "error",
        note=f"limit={body.limit}",
    )
    return {**result, "dry_run": False}
