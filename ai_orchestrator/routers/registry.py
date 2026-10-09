import logging
import os
import re
from dataclasses import asdict as _asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.agent_dispatch.agent_dispatch_router import agent_dispatch_router
from ai_orchestrator.agent_dispatch.agent_dispatch_router import resume_on_startup as _resume_agent_dispatch
from ai_orchestrator.auth.auth_router import auth_router
from ai_orchestrator.browser_tool.approval.approval_record_router import approval_record_router
from ai_orchestrator.connectors.google.gmail_reader import collect_to_inbox as _collect_gmail
from ai_orchestrator.connectors.naver_auth.session_router import router as naver_session_router
from ai_orchestrator.connectors.naver_blog.automation_router import blog_automation_router
from ai_orchestrator.connectors.naver_mail.bulk_router import naver_mail_bulk_router
from ai_orchestrator.connectors.naver_mail.mailbox_router import naver_mailbox_router
from ai_orchestrator.dev_reg.dev_reg_approval_read_router import dev_reg_approval_read_router
from ai_orchestrator.gongmu.gongmu_router import gongmu_router
from ai_orchestrator.routers.action_router import action_router
from ai_orchestrator.routers.admin_ui_router import admin_ui_router
from ai_orchestrator.routers.app_status_router import app_status_router
from ai_orchestrator.routers.chat_router import chat_router
from ai_orchestrator.routers.config_router import config_router
from ai_orchestrator.routers.ops_router import ops_router
from ai_orchestrator.scheduler.scheduled_job_router import scheduled_job_router
from ai_orchestrator.site_work import site_preflight_service as _site_preflight
from ai_orchestrator.site_work import site_task_map_explore_service as _site_explore
from ai_orchestrator.site_work import site_task_map_service as _site_map_service
from ai_orchestrator.site_work.ai_agent_router import ai_agent_router
from ai_orchestrator.site_work.site_onboarding_router import site_onboarding_router
from ai_orchestrator.site_work.site_task_map_router import site_task_map_router
from ai_orchestrator.user_data.user_data_contribution_router import user_data_contribution_router
from ai_orchestrator.vendor_directory.vendor_directory_router import vendor_directory_router
from ai_orchestrator.web_task.web_task_router import web_task_router
from scripts.entry import site_login_registry
from scripts.explorer import preflight_fetch, task_mapper, task_runner

from ..agent_hub.router.root import local_agent_router
from ..audit.audit_logger import log_event, read_recent_logs
from ..auth.desktop_session_router import desktop_session_router
from ..auth.user_auth_router import get_jwt_user, user_auth_router
from ..connectors.cdp_screen_router import cdp_screen_router
from ..connectors.community_router import community_router
from ..connectors.eum.router import eum_router
from ..connectors.gabia.router import gabia_router
from ..connectors.google.gmail_router import gmail_router
from ..connectors.google.router import google_router
from ..connectors.hanafax.router import hanafax_router
from ..connectors.hiworks.mail_router import hiworks_mail_router
from ..connectors.inquiry_router import inquiry_router
from ..connectors.instagram.instagram_dm_router import instagram_dm_router
from ..connectors.kakao.setup_router import kakao_setup_router
from ..connectors.kakao.skill_router import kakao_skill_router
from ..connectors.naver_blog.gonobi_router import gonobi_router
from ..connectors.naver_blog.naver_blog_router import naver_blog_router
from ..connectors.naver_cafe.naver_cafe_router import naver_cafe_router
from ..connectors.naver_mail.naver_mail_router import naver_mail_router
from ..connectors.naver_search.naver_news_router import naver_news_router
from ..connectors.naver_search.naver_openapi_setup_router import naver_openapi_setup_router
from ..connectors.naver_search.naver_search_router import naver_search_router
from ..connectors.public_media_router import public_media_router
from ..connectors.session_status_router import session_status_router
from ..connectors.smartstore.router import smartstore_router
from ..connectors.youtube.router import youtube_router
from ..core.models import TaskRequest
from tools.gates.approval import approve_token, issue_token, reject_token
from tools.gates.auth import require_role
from ..llm.planner import plan
from ..marketing.marketing_ops_router import marketing_ops_router
from ..notify.telegram_webhook import handle_telegram_update, handle_telegram_webhook
from ..sites.router import sites_router
from ..tasks.executor import execute
from ..tasks.inbox import get_inbox_item as _get_inbox_item
from ..tasks.inbox import read_recent_inbox

logger = logging.getLogger(__name__)


def resume_agent_dispatch_on_startup() -> bool:
    """서버 시작 시 승인된 채 끝나지 않은 AI 작업 분배가 있으면 러너를 다시 띄운다(asgi 가 이 모듈을 거쳐 부른다)."""
    return _resume_agent_dispatch()

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


# 사이트 업무(site_work)의 실행기 연결 — 조합 루트에서만 scripts.explorer 와 이어 준다(site_work 는 scripts 를 import 하지 않는다)
_site_explore.configure(task_mapper.run_request)  # 승인된 탐색의 실행기(브라우저 모듈은 실행 시점에만 불러온다)
_site_map_service.configure_runner(task_runner.run_task_in_browser)  # 지도 기반 업무 실행기(조회 업무 전용)
_site_preflight.configure_fetcher(preflight_fetch.fetch_text)  # 사전 조사 실행기(브라우저 없음)
site_login_registry.install()  # 사이트 로그인 등록표 — 서버 경로의 open_site(eum 커넥터 등)가 쓴다

router = APIRouter(prefix="/api/v1", tags=["orchestrator"])
router.include_router(auth_router)
router.include_router(desktop_session_router)  # 데스크톱 로컬 모드에서만 응답(그 외 404) — 첫 실행 등록·자동 세션
router.include_router(sites_router)
router.include_router(web_task_router)
router.include_router(dev_reg_approval_read_router)
router.include_router(local_agent_router)
router.include_router(admin_ui_router)
router.include_router(approval_record_router)
router.include_router(action_router)
router.include_router(naver_search_router)  # read-only naver search endpoints
router.include_router(naver_openapi_setup_router)  # 등록된 앱 Client ID/Secret 조회(설정화면 자동입력)
router.include_router(naver_news_router)  # read-only naver news scraping endpoints
router.include_router(naver_cafe_router)  # read-only naver cafe collection endpoints
router.include_router(community_router)  # 범용 커뮤니티 게시글 추출(휴리스틱→GPT)
router.include_router(inquiry_router)  # 문의 게시판(공개 접수 + 관리자 조회)
router.include_router(cdp_screen_router)  # CDP 라이브 화면(스크린샷 JPEG) — 콘솔 옆 실시간 작업 화면
router.include_router(naver_mail_router)  # naver mail compose/send endpoints
router.include_router(naver_session_router)  # naver session login pipeline
router.include_router(hiworks_mail_router)  # hiworks mail inbox/compose/send
router.include_router(eum_router)  # EUM 신규현장 수집 + 영업메일(하이웍스 발송)
router.include_router(gmail_router)  # gmail inbox/collect/compose/send
router.include_router(agent_dispatch_router)  # AI 작업 분배(계획 제안·사람 승인·병렬 실행, 관리자 전용, AI 허용 아님)
router.include_router(ai_agent_router)  # AI 에이전트 실행(run_claude_agent 자동 dispatch)
router.include_router(chat_router)  # AI 채팅 대화기록 CRUD(사용자 지시 '대화기록 저장')
router.include_router(ops_router)  # read-only ops center API
router.include_router(
    app_status_router
)  # read-only app status endpoints (APP_API_READONLY_ENDPOINTS_IMPLEMENTATION_01)
router.include_router(user_data_contribution_router)
router.include_router(youtube_router)
router.include_router(google_router)
router.include_router(smartstore_router)  # read-only smartstore catalog/history/form-fields
router.include_router(naver_blog_router)  # naver blog compose/drafts/seo
router.include_router(marketing_ops_router)  # 마케팅 운영실(기능 스위치 기본 꺼짐, R1 수리)
router.include_router(blog_automation_router)  # 블로그 자동 작성 규칙·승인·1회 실행(B단계: 로컬 초안까지)
router.include_router(naver_mailbox_router)  # 네이버 메일함 탭(폴더·목록·상세·첨부·보내기 2단계)
router.include_router(naver_mail_bulk_router)  # 메일 순차 대량 발송 승인서(관리자 전용, AI 허용 아님)
router.include_router(gongmu_router)  # 건설업 공무 업무판(현장·계약·업무·서류, 관리자 전용, AI 허용 아님)
router.include_router(vendor_directory_router)  # 벤더 공식 API 목록 조회(AI 허용 읽기 전용, 관리자 인증)
router.include_router(site_task_map_router)  # 사이트 업무 지도(탐색 결과를 업무 단위로 저장·조회, 관리자 전용, AI 는 읽기 2개만)
router.include_router(site_onboarding_router)  # 사이트 등록(온보딩): 로그인한 사이트를 호스트로 등록하고 최초 탐색으로 지도 생성, AI 는 읽기 2개만
router.include_router(scheduled_job_router)  # 사용자 예약 작업(목록·생성·일시중지·지금 실행·기록)
router.include_router(public_media_router)  # 외부 플랫폼(IG Graph API 등) 공개 미디어 서빙
router.include_router(user_auth_router)  # user signup/login/mypage
router.include_router(gabia_router)  # gabia dns/domain/login watch
router.include_router(gonobi_router)  # gonobi 블로그 수집·분류·조회
router.include_router(kakao_setup_router)  # 카카오 앱 등록 실시간 게이트
router.include_router(kakao_skill_router)  # 카카오 챗봇 스킬(오픈빌더) 응답 webhook
router.include_router(session_status_router)  # 앱별 로그인 세션 현황
router.include_router(hanafax_router)  # 하나팩스 팩스 발송
router.include_router(instagram_dm_router)  # 인스타그램 댓글->키워드->비공개DM 자동화

from .deploy_router import router as deploy_router  # noqa: E402
from .server_router import router as server_router  # noqa: E402

router.include_router(deploy_router)  # GitHub webhook → 자동 배포
router.include_router(server_router)  # 서버 인스턴스/헬스/배포 개요
router.include_router(config_router)  # 데스크톱 env 배포 + 로컬 재로딩

from ..connectors.grant_radar_router import grant_radar_router  # noqa: E402

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


_UNKNOWN_BUILD = "unknown"
_GIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_BUILD_TIME_RE = re.compile(r"^[0-9A-Za-z:+.\-_ ]{1,40}$")


def _build_value(env_name: str, pattern: re.Pattern[str]) -> str:
    """빌드 때 주입한 환경변수(GIT_SHA·BUILD_TIME)를 읽는다. 없거나 형식이 다르면 "unknown"."""
    value = os.environ.get(env_name, "").strip()
    return value if pattern.fullmatch(value) else _UNKNOWN_BUILD


@router.get("/health")
def health():
    # git_sha·build_time: 운영이 어느 커밋으로 빌드됐는지 공개 health 로 대조하기 위한 값(주입 방법: Dockerfile ARG·compose build.args)
    return {
        "status": "ok",
        "service": "haehan-ai-orchestrator",
        "git_sha": _build_value("GIT_SHA", _GIT_SHA_RE),
        "build_time": _build_value("BUILD_TIME", _BUILD_TIME_RE),
    }


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
