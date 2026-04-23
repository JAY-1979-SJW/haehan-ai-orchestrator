"""웹 작업 표준 실행 API.

엔드포인트:
  GET  /api/v1/web-tasks/registry  — 등록된 작업 목록 (admin/owner)
  POST /api/v1/web-tasks/run       — 작업 실행 요청 (admin/owner)

POST /run 동작:
  dry_run=true  → adapter.fill_form(page=None, dry_run=True) 로 검증·summary 반환.
                  approval 생성 없음, submit 없음.
  dry_run=false → pending approval 생성 + 텔레그램 발송 + 즉시 반환.
                  (status: pending_approval, 승인 후 실행은 기존 게이트 처리)

보안:
  - admin/owner 만 실행 허용
  - 미등록 provider/action_type → 404
  - validate_params 실패 → 422 (FORM_FIELD_MISSING)
  - params 원문 audit log / API 응답 노출 금지 (safe 필드만 허용)
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require_role
from .audit_logger import log_event
from .web_task_registry import get_entry, list_entries
from .sites.adapters.dev_reg_base import validate_params, ErrorCode
from . import dev_reg_approval as _dra
from .approval import issue_token_for_dev_reg
from .telegram_notifier import build_dev_reg_message
from . import telegram_sender as _ts

logger = logging.getLogger(__name__)

web_task_router = APIRouter(prefix="/web-tasks", tags=["web-tasks"])

# audit log / 응답에 포함 가능한 params 필드 화이트리스트
_SAFE_PARAM_KEYS: frozenset[str] = frozenset({
    "app_name", "company_name", "service_url", "redirect_uri",
    "contact_email", "purpose", "requested_scopes",
})


class WebTaskRunRequest(BaseModel):
    provider: str
    action_type: str
    params: dict = {}
    dry_run: bool = False


@web_task_router.get("/registry")
def get_web_task_registry(
    user: dict = Depends(require_role("admin", "owner")),
):
    """등록된 웹 작업 목록 반환."""
    return {"tasks": list_entries()}


@web_task_router.post("/run")
def run_web_task(
    body: WebTaskRunRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """웹 작업 실행 요청.

    dry_run=true : 검증 + summary 반환, approval 생성 없음, submit 없음.
    dry_run=false: pending approval 생성 + 텔레그램 발송 + 즉시 반환.
    """
    actor = user["actor"]
    role = user["role"]
    provider = body.provider.strip().lower()
    action_type = body.action_type.strip().lower()
    params = dict(body.params)

    # ── 1. 레지스트리 조회 ─────────────────────────────────────────────
    entry = get_entry(provider, action_type)
    if entry is None:
        log_event(
            "WEB_TASK_REJECTED_UNKNOWN_TASK", "web-task",
            action_type=action_type, actor=actor, role=role,
            note=f"provider={provider}",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "UNKNOWN_TASK",
                    "message": f"미등록 작업: {provider}/{action_type}"},
        )

    # ── 2. params 공통 검증 ───────────────────────────────────────────
    errors = validate_params(params)
    if errors:
        log_event(
            "WEB_TASK_VALIDATION_FAILED", "web-task",
            action_type=action_type, actor=actor, role=role,
            note=f"provider={provider}",
        )
        raise HTTPException(
            status_code=422,
            detail={"error": ErrorCode.FORM_FIELD_MISSING,
                    "message": "; ".join(errors)},
        )

    # ── 3a. dry_run 분기 ──────────────────────────────────────────────
    if body.dry_run:
        adapter = entry.adapter_class()
        fill_result = adapter.fill_form(None, {**params, "dry_run": True})

        log_event(
            "WEB_TASK_DRY_RUN_COMPLETED", "web-task",
            risk_level=entry.risk_level,
            action_type=action_type,
            actor=actor, role=role,
            note=f"provider={provider} success={fill_result.success}",
        )

        return {
            "dry_run": True,
            "provider": provider,
            "action_type": action_type,
            "risk_level": entry.risk_level,
            "requires_approval": entry.requires_approval,
            "success": fill_result.success,
            "summary": fill_result.summary,
            "field_names": fill_result.field_names,
            "target_url": fill_result.target_url,
            "error": fill_result.error,
            "error_code": fill_result.error_code,
        }

    # ── 3b. real_run: pending approval 생성 ──────────────────────────
    task_id = f"wt-{uuid.uuid4().hex[:12]}"

    # dry_run 으로 summary 생성 (page=None, DOM 조작 없음)
    adapter = entry.adapter_class()
    fill_result = adapter.fill_form(None, {**params, "dry_run": True})
    summary = (fill_result.summary if fill_result.success
               else f"[summary 생성 실패] {fill_result.error}")

    log_event(
        "WEB_TASK_RUN_REQUESTED", task_id,
        risk_level=entry.risk_level,
        action_type=action_type,
        target=fill_result.target_url,
        actor=actor, role=role,
        note=f"provider={provider}",
    )

    # 승인 토큰 발행
    token = issue_token_for_dev_reg(
        task_id=task_id,
        requested_by=actor,
        risk_level=entry.risk_level,
        ttl_minutes=30,
    )

    # pending 레코드 생성
    _dra.create_pending(
        task_id=task_id,
        token_id=token.token_id,
        provider=provider,
        action_type=action_type,
        risk_level=entry.risk_level,
        summary=summary,
        target_url=fill_result.target_url,
        screenshot_path="",
        requested_by=actor,
        expires_at=token.expires_at,
    )

    log_event(
        "WEB_TASK_PENDING_APPROVAL_CREATED", task_id,
        risk_level=entry.risk_level,
        action_type=action_type,
        target=fill_result.target_url,
        actor=actor, role=role,
        token_id=token.token_id,
        note=f"provider={provider}",
    )

    # 텔레그램 승인 요청 발송
    msg = build_dev_reg_message(
        task_id=task_id,
        provider=provider,
        action_type=action_type,
        summary=summary,
        risk_level=entry.risk_level,
        target_url=fill_result.target_url,
        expires_at=token.expires_at,
        token_id=token.token_id,
    )
    send_result = _ts.send_message(text=msg["text"], reply_markup=msg["reply_markup"])
    tg_msg_id = str((send_result.get("result") or {}).get("message_id", ""))
    _dra.mark_telegram_sent(task_id, message_id=tg_msg_id)

    return {
        "dry_run": False,
        "status": "pending_approval",
        "task_id": task_id,
        "provider": provider,
        "action_type": action_type,
        "risk_level": entry.risk_level,
        "requires_approval": entry.requires_approval,
        "expires_at": token.expires_at,
    }
