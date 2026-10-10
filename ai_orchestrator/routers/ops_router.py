"""운영센터 read-only 집계 API.

엔드포인트 (모두 GET / read-only):
  GET /api/v1/ops/summary         — 대시보드 메트릭 집계
  GET /api/v1/ops/approvals       — 승인 대기 목록
  GET /api/v1/ops/web-tasks       — 웹 작업 레지스트리 목록
  GET /api/v1/ops/audit-events    — 감사 이벤트 최근 N건
  GET /api/v1/ops/agents          — 로컬 에이전트 상태 목록
  GET /api/v1/ops/external-work   — 외부 웹 업무 분류 목록
  GET /api/v1/ops/integrations    — 연동 현황 계산

보안 원칙:
  - 모두 GET / read-only. POST/PUT/DELETE 없음.
  - admin/owner 만 접근 가능.
  - secret/token/password/cookie/session 노출 금지.
  - 외부 API 호출 없음. Telegram 발송 없음.
  - DB write 없음. schema 변경 없음.
  - 기존 API 응답 key/status code 변경 없음.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ai_orchestrator.agent_hub.registry import facade as _reg
from ai_orchestrator.audit.audit_logger import read_recent_logs as _read_logs
from ai_orchestrator.auth.user_auth_router import get_jwt_user
from ai_orchestrator.dev_reg.dev_reg_approval import list_pending as _list_pending
from ai_orchestrator.tasks.external_work_registry import (
    list_external_works as _list_external,
)
from ai_orchestrator.web_task.web_task_registry import list_entries as _list_web_tasks

logger = logging.getLogger(__name__)

ops_router = APIRouter(prefix="/ops", tags=["ops-readonly"])


# ─── 승인 대기 ────────────────────────────────────────────────────────────────


@ops_router.get("/approvals")
def get_ops_approvals(
    user: dict = Depends(get_jwt_user),
):
    """승인 대기 목록 — dev_reg_approval.list_pending() 기반."""
    try:
        pending = _list_pending()
        items = []
        for rec in pending:
            items.append(
                {
                    "taskId": rec.get("task_id", ""),
                    "taskName": _build_task_name(rec),
                    "provider": rec.get("provider", ""),
                    "actionType": rec.get("action_type", ""),
                    "riskLevel": rec.get("risk_level", "medium"),
                    "requestedAt": rec.get("created_at", ""),
                    "expiresAt": rec.get("expires_at", ""),
                    "status": "pending_approval",
                    "requestedBy": rec.get("actor", "unknown"),
                }
            )
        return {"items": items, "source": "live"}
    except Exception as e:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("ops/approvals 조회 실패: %s", e)
        return {"items": [], "source": "error", "error": str(e)}


def _build_task_name(rec: dict) -> str:
    provider = rec.get("provider", "")
    action_type = rec.get("action_type", "")
    summary = rec.get("summary", "")
    if summary:
        return summary[:80]
    if provider and action_type:
        return f"{provider}/{action_type}"
    return rec.get("task_id", "-")


# ─── 웹 작업 레지스트리 ──────────────────────────────────────────────────────


@ops_router.get("/web-tasks")
def get_ops_web_tasks(
    user: dict = Depends(get_jwt_user),
):
    """등록된 웹 작업 목록 — web_task_registry.list_entries() 기반."""
    try:
        entries = _list_web_tasks()
        tasks = []
        for e in entries:
            status = "ready"
            if not e.get("read_only") and e.get("requires_approval"):
                status = "ready"  # approval gate 완비
            tasks.append(
                {
                    "taskKey": e["task_key"],
                    "provider": e["provider"],
                    "actionType": e["action_type"],
                    "description": e["description"],
                    "executionLocation": "LOCAL_AGENT",
                    "riskLevel": e["risk_level"],
                    "requiresApproval": e["requires_approval"],
                    "dryRunSupported": True,
                    "classification": "WEB_TASK_REGISTRY",
                    "status": status,
                }
            )
        return {"tasks": tasks, "source": "live"}
    except Exception as e:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("ops/web-tasks 조회 실패: %s", e)
        return {"tasks": [], "source": "error", "error": str(e)}


# ─── 감사 이벤트 ─────────────────────────────────────────────────────────────


@ops_router.get("/audit-events")
def get_ops_audit_events(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_jwt_user),
):
    """감사 이벤트 최근 N건 — audit_logger.read_recent_logs() 기반."""
    try:
        logs = _read_logs(limit=limit)
        events = []
        for i, entry in enumerate(reversed(logs)):
            event_type = entry.get("event_type", "")
            raw_status = entry.get("decision", "")
            status = _map_audit_status(raw_status, event_type)
            events.append(
                {
                    "eventId": f"evt-{i:04d}",
                    "eventType": event_type,
                    "taskId": entry.get("task_id", "-"),
                    "status": status,
                    "timestamp": entry.get("timestamp", ""),
                    "actor": entry.get("actor", "-"),
                    "summary": _build_event_summary(entry),
                }
            )
        return {"events": events, "source": "live"}
    except Exception as e:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("ops/audit-events 조회 실패: %s", e)
        return {"events": [], "source": "error", "error": str(e)}


def _map_audit_status(decision: str, event_type: str) -> str:
    if "FAIL" in event_type or "DENIED" in event_type or "BLOCKED" in event_type:
        return "error"
    if "WARN" in event_type or "RATE_LIMITED" in event_type or "TIMEOUT" in event_type:
        return "warn"
    if "REJECTED" in event_type:
        return "warn"
    if decision and any(k in decision.upper() for k in ("BLOCKED", "FAIL", "ERROR")):
        return "error"
    return "ok"


def _build_event_summary(entry: dict) -> str:
    parts = []
    event_type = entry.get("event_type", "")
    action_type = entry.get("action_type", "")
    decision = entry.get("decision", "")
    note = entry.get("note", "")
    if action_type:
        parts.append(action_type)
    if decision and decision != action_type:
        parts.append(decision[:60])
    if note:
        parts.append(note[:60])
    if not parts:
        parts.append(event_type)
    return " — ".join(parts)[:120]


# ─── 로컬 에이전트 상태 ──────────────────────────────────────────────────────


@ops_router.get("/agents")
def get_ops_agents(
    user: dict = Depends(get_jwt_user),
):
    """로컬 에이전트 상태 목록 — local_agent_registry.list_agents() 기반."""
    try:
        agents_raw = _reg.list_agents()
        agents = []
        for a in agents_raw:
            # to_safe() 는 token_hash/device_token 제외하고 반환
            status_val = a.get("status", "offline")
            agents.append(
                {
                    "agentId": a.get("agent_id", ""),
                    "agentName": a.get("name", a.get("agent_id", "")),
                    "status": _map_agent_status(status_val),
                    "lastHeartbeat": a.get("last_seen_at", a.get("registered_at", "")),
                    "canReceiveTasks": status_val not in ("offline", "error"),
                    "userDirectRequired": False,
                    "serverExecutable": False,
                    "blockingPolicy": None,
                }
            )
        return {"agents": agents, "source": "live"}
    except Exception as e:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("ops/agents 조회 실패: %s", e)
        return {"agents": [], "source": "error", "error": str(e)}


def _map_agent_status(raw: str) -> str:
    _map = {
        "online": "online",
        "active": "online",
        "idle": "idle",
        "waiting": "idle",
        "busy": "busy",
        "running": "busy",
        "offline": "offline",
        "disconnected": "offline",
        "error": "error",
        "failed": "error",
    }
    return _map.get(raw.lower() if raw else "", "offline")


# ─── 외부 웹 업무 ─────────────────────────────────────────────────────────────


@ops_router.get("/external-work")
def get_ops_external_work(
    provider: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    user: dict = Depends(get_jwt_user),
):
    """외부 웹 업무 분류 목록 — external_work_registry 기반."""
    try:
        entries = _list_external(provider=provider, classification=classification)
        return {"entries": entries, "total": len(entries), "source": "live"}
    except Exception as e:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("ops/external-work 조회 실패: %s", e)
        return {"entries": [], "total": 0, "source": "error", "error": str(e)}


# ─── 연동 현황 ───────────────────────────────────────────────────────────────
# 참고: 이 목록은 domain/integrations_static.py 에도 동일하게 유지된다
# (domain/model_adapters.py 가 참조하는 L1 공유 사본).
# ops_router.py 자체는 test_ops_router_read_only_20260516.py 가 소스 텍스트에서
# "cad-app" 리터럴 존재를 직접 검사하므로, 여기 원본도 그대로 유지한다
# (레이어 위반 domain/model_adapters.py -> ops_router.py 는 미해결로 남김 — 결정 로그 참조).

_STATIC_INTEGRATIONS = [
    {
        "key": "naver-search",
        "name": "Naver 검색 (read-only)",
        "classification": "SERVER_READONLY_ALLOWED",
        "connected": True,
        "authMethod": "none",
        "notes": "/api/v1/external/naver/* 3개 endpoint 활성화됨",
    },
    {
        "key": "naver-local-agent",
        "name": "Naver 로컬 에이전트 업무",
        "classification": "LOCAL_AGENT_REQUIRED",
        "connected": False,
        "authMethod": "browser_session",
        "notes": "로컬 에이전트 + 사전 로그인 필요",
        "action": "로컬 에이전트 설정",
    },
    {
        "key": "google-oauth",
        "name": "Google OAuth/API",
        "classification": "OFFICIAL_API_OR_OAUTH_REQUIRED",
        "connected": False,
        "authMethod": "oauth",
        "notes": "credentials.json + token.json 설정 필요",
        "action": "OAuth 설정 시작",
    },
    {
        "key": "telegram",
        "name": "Telegram 알림",
        "classification": "IN_SCOPE",
        "connected": True,
        "authMethod": "bot_token",
        "notes": "BOT_TOKEN env 설정됨. 승인 알림 발송 활성화",
    },
    {
        "key": "cad-app",
        "name": "CAD 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
    {
        "key": "hwpx-app",
        "name": "HWPX 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
    {
        "key": "excel-app",
        "name": "Excel/Office 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
]


@ops_router.get("/integrations")
def get_ops_integrations(
    user: dict = Depends(get_jwt_user),
):
    """연동 현황 — static registry 기반 (연결 여부는 runtime 감지 X, 정책 기준)."""
    return {"integrations": _STATIC_INTEGRATIONS, "source": "static"}


# ─── 대시보드 메트릭 집계 ────────────────────────────────────────────────────


@ops_router.get("/summary")
def get_ops_summary(
    user: dict = Depends(get_jwt_user),
):
    """대시보드 메트릭 집계 — 각 모듈 상태를 읽어 집계."""
    try:
        pending_count = len(_list_pending())
    except Exception as err:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("대시보드 승인 대기 집계 실패: %s", type(err).__name__)
        pending_count = 0

    try:
        agents_raw = _reg.list_agents()
        online_count = sum(1 for a in agents_raw if _map_agent_status(a.get("status", "")) == "online")
    except Exception as err:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("대시보드 에이전트 집계 실패: %s", type(err).__name__)
        online_count = 0
        agents_raw = []

    try:
        web_task_count = len(_list_web_tasks())
    except Exception as err:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("대시보드 웹작업 집계 실패: %s", type(err).__name__)
        web_task_count = 0

    try:
        external_count = len(_list_external())
    except Exception as err:  # noqa: BLE001 - 운영 대시보드 조회 API - 승인/웹작업/감사이벤트/에이전트 현황을 읽기전용으로 집계, 실패시 빈 리스트/0건으로 폴백하고 warning 로그만 남김. 판정/차단 로직 없음
        logger.warning("대시보드 외부작업 집계 실패: %s", type(err).__name__)
        external_count = 0

    approval_status: str = "WARN" if pending_count > 0 else "PASS"

    metrics = [
        {"label": "웹 작업 등록", "value": str(web_task_count), "sub": "건", "status": "PASS"},
        {"label": "승인 대기", "value": str(pending_count), "sub": "건", "status": approval_status},
        {"label": "외부 웹 업무", "value": str(external_count), "sub": "건 분류됨", "status": "PASS"},
        {"label": "로컬 에이전트", "value": str(online_count), "sub": "대 온라인", "status": "PASS"},
        {"label": "연동 서비스", "value": str(len(_STATIC_INTEGRATIONS)), "sub": "건", "status": "PASS"},
        {
            "label": "게이트",
            "value": "PASS" if pending_count == 0 else "WARN",
            "sub": None,
            "status": approval_status,
        },
    ]
    return {"metrics": metrics, "source": "live"}


__all__ = ["ops_router"]
