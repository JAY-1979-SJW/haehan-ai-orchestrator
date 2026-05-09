import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .models import TaskRequest

logger = logging.getLogger(__name__)
from .planner import plan
from .executor import execute
from .approval import issue_token, approve_token, validate_token, reject_token
from .audit_logger import log_event, read_recent_logs
from .auth import require_role
from .telegram_webhook import handle_telegram_webhook, handle_telegram_update
from .inbox import read_recent_inbox, get_inbox_item as _get_inbox_item
from .gmail_reader import collect_to_inbox as _collect_gmail
from dataclasses import asdict as _asdict
from .sites.router import sites_router
from .cad.router import cad_router
from .web_task_router import web_task_router
from .local_agent_router import local_agent_router
from .admin_ui_router import admin_ui_router
from .auth_router import auth_router
from .browser_tool.approval_record_router import approval_record_router
from .action_router import action_router
from .cad_ai_router import cad_ai_router

router = APIRouter(prefix="/api/v1", tags=["orchestrator"])
router.include_router(auth_router)
router.include_router(sites_router)
router.include_router(cad_router)
router.include_router(cad_ai_router)
router.include_router(web_task_router)
router.include_router(local_agent_router)
router.include_router(admin_ui_router)
router.include_router(approval_record_router)
router.include_router(action_router)


class TaskSubmit(BaseModel):
    task_id: str
    source: str
    action_type: str
    target: str
    description: str
    payload: dict = {}
    # 호환을 위해 필드는 유지하지만 서버에서 신뢰하지 않고 current_user.actor 로 덮어쓴다.
    requested_by: Optional[str] = None


class ApproveRequest(BaseModel):
    # 호환을 위해 필드는 유지하나 서버는 current_user.actor / current_user.role 만 신뢰한다.
    approved_by: Optional[str] = None
    role: Optional[str] = None


class RejectRequest(BaseModel):
    # 호환을 위해 필드는 유지하나 서버는 current_user.actor / current_user.role 만 신뢰한다.
    rejected_by: Optional[str] = None
    role: Optional[str] = None
    reason: str = ""


class TelegramWebhookBody(BaseModel):
    telegram_user_id: str
    action: str
    task_id: str
    token_id: str
    reason: str = ""


_REJECT_STATUS_HTTP = {
    "rejected": 200,
    "not_found": 404,
    "task_mismatch": 400,
    "already_used": 409,
    "expired": 410,
    "forbidden": 403,
    "rate_limited": 429,
}

_REJECT_STATUS_AUDIT = {
    "rejected": "APPROVAL_REJECTED",
    "not_found": "APPROVAL_REJECT_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_REJECT_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_REJECT_FORBIDDEN",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}

_STATUS_HTTP = {
    "approved": 200,
    "not_found": 404,
    "task_mismatch": 400,
    "already_used": 409,
    "expired": 410,
    "forbidden": 403,
    "rate_limited": 429,
}

_STATUS_AUDIT = {
    "approved": "APPROVAL_GRANTED",
    "not_found": "APPROVAL_INVALID_TOKEN",
    "task_mismatch": "APPROVAL_INVALID_TOKEN",
    "already_used": "APPROVAL_ALREADY_USED",
    "expired": "APPROVAL_EXPIRED",
    "forbidden": "APPROVAL_DENIED",
    "rate_limited": "APPROVAL_RATE_LIMITED",
}


@router.get("/health")
def health():
    return {"status": "ok", "service": "haehan-ai-orchestrator"}


@router.post("/tasks")
def submit_task(
    body: TaskSubmit,
    user: dict = Depends(require_role("operator", "admin", "owner")),
):
    # 클라이언트가 주장한 requested_by 는 무시하고 인증된 actor 로 덮어쓴다.
    actor = user["actor"]
    role = user["role"]
    data = body.model_dump()
    data["requested_by"] = actor
    req = TaskRequest(**data)
    logger.info("작업 수신 | task=%s | action=%s | actor=%s | role=%s",
                req.task_id, req.action_type, actor, role)
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type,
              target=req.target, actor=actor, role=role)

    risk, ep = plan(req)
    log_event("PLAN_CREATED", req.task_id, risk_level=risk.risk_level,
              action_type=req.action_type, allowed=ep.allowed,
              requires_approval=ep.requires_approval, actor="system")

    token_id = None
    if ep.requires_approval and ep.allowed:
        token = issue_token(req, risk, ttl_minutes=30)
        token_id = token.token_id
        log_event("APPROVAL_ISSUED", req.task_id, risk_level=risk.risk_level,
                  action_type=req.action_type, decision="issued",
                  actor=actor, role=role, note=f"token_id={token_id}")

    result = execute(ep, req=req, risk_level=risk.risk_level)
    _exec_event = "DRY_RUN_RETURNED"
    if result.startswith("BLOCKED:rate_limited"):
        _exec_event = "EXECUTION_RATE_LIMITED"
    elif result.startswith("BLOCKED:execution_timeout"):
        _exec_event = "EXECUTION_TIMEOUT"
    log_event(_exec_event, req.task_id, risk_level=risk.risk_level,
              action_type=req.action_type, allowed=ep.allowed,
              decision=result, actor="executor")

    return {
        "task_id": req.task_id,
        "risk_level": risk.risk_level,
        "allowed": ep.allowed,
        "requires_approval": ep.requires_approval,
        "approval_token_id": token_id,
        "status": result,
        "steps": ep.steps,
        "blocked_reasons": ep.blocked_reasons,
    }


@router.post("/tasks/{task_id}/approve")
def approve_task(
    task_id: str,
    token_id: str,
    body: ApproveRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    # body.approved_by / body.role 은 신뢰하지 않는다. current_user 로 단일화.
    actor = user["actor"]
    role = user["role"]
    token, status = approve_token(token_id, task_id, actor, role)
    audit_event = _STATUS_AUDIT.get(status, "APPROVAL_DENIED")
    log_event(audit_event, task_id,
              token_id=token_id, actor=actor, role=role,
              decision=status, risk_level=token.risk_level)
    http_status = _STATUS_HTTP.get(status, 400)
    if http_status != 200:
        raise HTTPException(status_code=http_status, detail={"status": status})
    return {"token_id": token_id, "status": status, "approved_by": actor}


@router.post("/tasks/{task_id}/reject")
def reject_task(
    task_id: str,
    token_id: str,
    body: RejectRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    # body.rejected_by / body.role 은 신뢰하지 않는다. current_user 로 단일화.
    actor = user["actor"]
    role = user["role"]
    token, status = reject_token(token_id, task_id, actor, role, body.reason)
    audit_event = _REJECT_STATUS_AUDIT.get(status, "APPROVAL_REJECTED")
    log_event(audit_event, task_id,
              token_id=token_id, actor=actor, role=role,
              decision=status, risk_level=token.risk_level, note=body.reason)
    http_status = _REJECT_STATUS_HTTP.get(status, 400)
    if http_status != 200:
        raise HTTPException(status_code=http_status, detail={"status": status})
    return {"token_id": token_id, "status": status, "rejected_by": actor}


_TG_WEBHOOK_HTTP = {
    "invalid_payload": 400, "invalid_action": 400, "user_not_found": 403,
    "forbidden": 403, "rate_limited": 429, "not_found": 404,
    "already_used": 409, "expired": 410, "task_mismatch": 400,
}


@router.post("/webhooks/telegram")
def telegram_webhook(body: dict):
    """flat payload 와 Telegram Update(callback_query) 둘 다 수용."""
    if isinstance(body, dict) and "callback_query" in body:
        result = handle_telegram_update(body)
    else:
        result = handle_telegram_webhook(body or {})

    if not result.get("success"):
        http_code = _TG_WEBHOOK_HTTP.get(result.get("status", ""), 400)
        raise HTTPException(status_code=http_code, detail=result)
    return result


@router.get("/inbox")
def get_inbox_list(limit: int = 20):
    limit = max(1, min(limit, 500))
    return read_recent_inbox(limit=limit)


@router.get("/inbox/{item_id}")
def get_inbox_item_endpoint(item_id: str):
    item = _get_inbox_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"inbox item 없음: {item_id}")
    return _asdict(item)


@router.post("/inbox/email/fetch")
def fetch_email_inbox(
    max_results: int = 50,
    hours: int = 24,
    user: dict = Depends(require_role("admin", "owner")),
):
    max_results = max(1, min(max_results, 200))
    hours = max(1, min(hours, 168))
    summary = _collect_gmail(max_results=max_results, hours=hours)
    return summary


@router.get("/logs")
def get_logs(limit: int = 20):
    limit = max(1, min(limit, 500))
    return read_recent_logs(limit=limit)
