import logging
from dataclasses import asdict as _asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .action_router import action_router
from .admin_ui_router import admin_ui_router
from .agent_ai_proxy_router import agent_ai_proxy_router
from .app_status_router import app_status_router
from .approval import approve_token, issue_token, reject_token
from .audit_logger import log_event, read_recent_logs
from .auth import require_role
from .auth_router import auth_router
from .browser_tool.approval_record_router import approval_record_router
from .config_router import config_router
from .connectors.community_router import community_router
from .connectors.eum_router import eum_router
from .connectors.gabia_router import gabia_router
from .connectors.gmail_router import gmail_router
from .connectors.google_router import google_router
from .connectors.hanafax_router import hanafax_router
from .connectors.hiworks_mail_router import hiworks_mail_router
from .connectors.inquiry_router import inquiry_router
from .connectors.kakao_setup_router import kakao_setup_router
from .connectors.naver_blog_router import naver_blog_router
from .connectors.naver_cafe_router import naver_cafe_router
from .connectors.naver_mail_router import naver_mail_router
from .connectors.naver_news_router import naver_news_router
from .connectors.naver_search_router import naver_search_router
from .connectors.naver_session_router import router as naver_session_router
from .connectors.session_status_router import session_status_router
from .connectors.smartstore_router import smartstore_router
from .connectors.user_auth_router import get_jwt_user, user_auth_router
from .connectors.youtube_router import youtube_router
from .executor import execute
from .gmail_reader import collect_to_inbox as _collect_gmail
from .inbox import get_inbox_item as _get_inbox_item
from .inbox import read_recent_inbox
from .local_agent_router import local_agent_router
from .models import TaskRequest
from .ops_router import ops_router
from .planner import plan
from .sites.router import sites_router
from .telegram_webhook import handle_telegram_update, handle_telegram_webhook
from .user_data_contribution_router import user_data_contribution_router
from .web_task_router import web_task_router

logger = logging.getLogger(__name__)

# ── Phase 1-R: feature flag OFF constants (default: disabled) ────────────
LEGACY_5050_ROUTER_TOUCH_PHASE = "PHASE_1R"
LEGACY_5050_ROUTER_TOUCH_ENABLED = False
LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED = False
LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED = False
LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED = False

# ── POST /tasks dry-run gate (default: True — 실제 token 발행/execute 차단) ─
# False로 전환하려면 대표 명시 승인 후 별도 commit으로 변경.
POST_TASKS_DRY_RUN_ENABLED = True


def _legacy_5050_should_use_route_wiring(route_id: str) -> bool:
    """Phase 1-R guard helper. 기본 OFF — 기존 route 동작 보존."""
    _flags = {
        "INBOX_EMAIL_FETCH": LEGACY_5050_INBOX_EMAIL_FETCH_ROUTE_WIRING_ENABLED,
        "TASK_APPROVE": LEGACY_5050_TASK_APPROVE_ROUTE_WIRING_ENABLED,
        "TASK_REJECT": LEGACY_5050_TASK_REJECT_ROUTE_WIRING_ENABLED,
    }
    return _flags.get(route_id, False)


router = APIRouter(prefix="/api/v1", tags=["orchestrator"])
router.include_router(auth_router)
router.include_router(sites_router)
router.include_router(web_task_router)
router.include_router(local_agent_router)
router.include_router(agent_ai_proxy_router)
router.include_router(admin_ui_router)
router.include_router(approval_record_router)
router.include_router(action_router)
router.include_router(naver_search_router)  # read-only naver search endpoints
router.include_router(naver_news_router)  # read-only naver news scraping endpoints
router.include_router(naver_cafe_router)  # read-only naver cafe collection endpoints
router.include_router(community_router)  # 범용 커뮤니티 게시글 추출(휴리스틱→GPT)
router.include_router(inquiry_router)  # 문의 게시판(공개 접수 + 관리자 조회)
router.include_router(naver_mail_router)  # naver mail compose/send endpoints
router.include_router(naver_session_router)  # naver session login pipeline
router.include_router(hiworks_mail_router)  # hiworks mail inbox/compose/send
router.include_router(eum_router)  # EUM 신규현장 수집 + 영업메일(하이웍스 발송)
router.include_router(gmail_router)  # gmail inbox/collect/compose/send
router.include_router(ops_router)  # read-only ops center API
router.include_router(
    app_status_router
)  # read-only app status endpoints (APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01)
router.include_router(user_data_contribution_router)
router.include_router(youtube_router)
router.include_router(google_router)
router.include_router(smartstore_router)  # read-only smartstore catalog/history/form-fields
router.include_router(naver_blog_router)  # naver blog compose/drafts/seo
router.include_router(user_auth_router)  # user signup/login/mypage
router.include_router(gabia_router)  # gabia dns/domain/login watch
router.include_router(kakao_setup_router)  # 카카오 앱 등록 실시간 게이트
router.include_router(session_status_router)  # 앱별 로그인 세션 현황
router.include_router(hanafax_router)  # 하나팩스 팩스 발송

from .routers.deploy_router import router as deploy_router  # noqa: E402
from .routers.server_router import router as server_router  # noqa: E402

router.include_router(deploy_router)  # GitHub webhook → 자동 배포
router.include_router(server_router)  # 서버 인스턴스/헬스/배포 개요
router.include_router(config_router)  # 데스크톱 env 배포 + 로컬 재로딩

from .connectors.grant_radar_router import grant_radar_router  # noqa: E402

router.include_router(grant_radar_router)  # 정부 지원사업 레이더 (탐색·보고서)


class TaskSubmit(BaseModel):
    task_id: str
    source: str
    action_type: str
    target: str
    description: str
    payload: dict = {}
    # 호환을 위해 필드는 유지하지만 서버에서 신뢰하지 않고 current_user.actor 로 덮어쓴다.
    requested_by: str | None = None


class ApproveRequest(BaseModel):
    # 호환을 위해 필드는 유지하나 서버는 current_user.actor / current_user.role 만 신뢰한다.
    approved_by: str | None = None
    role: str | None = None


class RejectRequest(BaseModel):
    # 호환을 위해 필드는 유지하나 서버는 current_user.actor / current_user.role 만 신뢰한다.
    rejected_by: str | None = None
    role: str | None = None
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
    logger.info("작업 수신 | task=%s | action=%s | actor=%s | role=%s", req.task_id, req.action_type, actor, role)
    log_event("TASK_RECEIVED", req.task_id, action_type=req.action_type, target=req.target, actor=actor, role=role)

    risk, ep = plan(req)
    log_event(
        "PLAN_CREATED",
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        requires_approval=ep.requires_approval,
        actor="system",
    )

    # dry-run gate: token 발행 및 실제 execute 차단
    if POST_TASKS_DRY_RUN_ENABLED and ep.requires_approval and ep.allowed:
        log_event(
            "DRY_RUN_GATE_BLOCKED",
            req.task_id,
            risk_level=risk.risk_level,
            action_type=req.action_type,
            allowed=ep.allowed,
            requires_approval=ep.requires_approval,
            actor=actor,
            note="POST_TASKS_DRY_RUN_ENABLED=True: token 발행 차단",
        )
        return {
            "task_id": req.task_id,
            "risk_level": risk.risk_level,
            "allowed": ep.allowed,
            "requires_approval": ep.requires_approval,
            "approval_token_id": None,
            "status": "DRY_RUN: would issue token — gate active",
            "steps": ep.steps,
            "blocked_reasons": ep.blocked_reasons,
            "dry_run": True,
        }

    token_id = None
    if ep.requires_approval and ep.allowed:
        token = issue_token(req, risk, ttl_minutes=30)
        token_id = token.token_id
        log_event(
            "APPROVAL_ISSUED",
            req.task_id,
            risk_level=risk.risk_level,
            action_type=req.action_type,
            decision="issued",
            actor=actor,
            role=role,
            note=f"token_id={token_id}",
        )

    result = execute(ep, req=req, risk_level=risk.risk_level)
    _exec_event = "DRY_RUN_RETURNED"
    if result.startswith("BLOCKED:rate_limited"):
        _exec_event = "EXECUTION_RATE_LIMITED"
    elif result.startswith("BLOCKED:execution_timeout"):
        _exec_event = "EXECUTION_TIMEOUT"
    log_event(
        _exec_event,
        req.task_id,
        risk_level=risk.risk_level,
        action_type=req.action_type,
        allowed=ep.allowed,
        decision=result,
        actor="executor",
    )

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
    if _legacy_5050_should_use_route_wiring("TASK_APPROVE"):
        raise RuntimeError("PHASE_1R route wiring is disabled by default")
    # body.approved_by / body.role 은 신뢰하지 않는다. current_user 로 단일화.
    actor = user["actor"]
    role = user["role"]
    token, status = approve_token(token_id, task_id, actor, role)
    audit_event = _STATUS_AUDIT.get(status, "APPROVAL_DENIED")
    log_event(
        audit_event, task_id, token_id=token_id, actor=actor, role=role, decision=status, risk_level=token.risk_level
    )
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
    if _legacy_5050_should_use_route_wiring("TASK_REJECT"):
        raise RuntimeError("PHASE_1R route wiring is disabled by default")
    # body.rejected_by / body.role 은 신뢰하지 않는다. current_user 로 단일화.
    actor = user["actor"]
    role = user["role"]
    token, status = reject_token(token_id, task_id, actor, role, body.reason)
    audit_event = _REJECT_STATUS_AUDIT.get(status, "APPROVAL_REJECTED")
    log_event(
        audit_event,
        task_id,
        token_id=token_id,
        actor=actor,
        role=role,
        decision=status,
        risk_level=token.risk_level,
        note=body.reason,
    )
    http_status = _REJECT_STATUS_HTTP.get(status, 400)
    if http_status != 200:
        raise HTTPException(status_code=http_status, detail={"status": status})
    return {"token_id": token_id, "status": status, "rejected_by": actor}


_TG_WEBHOOK_HTTP = {
    "invalid_payload": 400,
    "invalid_action": 400,
    "user_not_found": 403,
    "forbidden": 403,
    "rate_limited": 429,
    "not_found": 404,
    "already_used": 409,
    "expired": 410,
    "task_mismatch": 400,
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
def get_inbox_list(
    limit: int = 20,
    user: dict = Depends(get_jwt_user),
):
    limit = max(1, min(limit, 500))
    return read_recent_inbox(limit=limit)


@router.get("/inbox/{item_id}")
def get_inbox_item_endpoint(
    item_id: str,
    user: dict = Depends(get_jwt_user),
):
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
    if _legacy_5050_should_use_route_wiring("INBOX_EMAIL_FETCH"):
        raise RuntimeError("PHASE_1R route wiring is disabled by default")
    max_results = max(1, min(max_results, 200))
    hours = max(1, min(hours, 168))
    summary = _collect_gmail(max_results=max_results, hours=hours)
    return summary


@router.get("/logs")
def get_logs(
    limit: int = 20,
    user: dict = Depends(get_jwt_user),
):
    limit = max(1, min(limit, 500))
    return read_recent_logs(limit=limit)
