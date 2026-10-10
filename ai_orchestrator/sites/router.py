"""사이트 자동화 1단계 엔드포인트.

- GET  /site-health                     (admin, owner)
- GET  /site-health/{site_name}         (admin, owner)
- GET  /connectors                      (admin, owner)
- POST /site-tasks/dry-run              (operator, admin, owner)

기존 /health, /tasks, /approve, /reject 와 충돌하지 않도록 별도 prefix 없이
api/v1 아래에 공존시킨다 (main router 가 prefix="/api/v1" 유지).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tools.gates.auth import require_role

from ..audit.audit_logger import log_event
from ..auth.user_auth_router import get_jwt_user
from ..tasks.external_work_registry import list_site_catalog
from . import registry
from .health import SiteHealthService
from .models import SiteTask

logger = logging.getLogger(__name__)

sites_router = APIRouter(tags=["sites"])
_health_service = SiteHealthService()


class SiteTaskDryRunBody(BaseModel):
    task_id: str
    target_site: str
    action: str
    params: dict = Field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = False
    execution_mode: str = "dry_run"
    # requested_by / actor_role 은 body 에서 받지 않는다.
    # 서버가 current_user 로 덮어쓴다 (body.role 스푸핑 방어 원칙 유지).


@sites_router.get("/sites/catalog")
def site_catalog(user: dict = Depends(get_jwt_user)):
    """사이트 카탈로그 — 로그인(승인)된 사용자가 '쓸 사이트'를 고를 목록.

    사용자 선택/설정은 클라이언트 로컬에 저장(순수 로컬 원칙). 서버는 목록만 제공.
    """
    return {"sites": list_site_catalog()}


@sites_router.get("/connectors")
def list_connectors(user: dict = Depends(require_role("admin", "owner"))):
    data = _health_service.list_connectors()
    log_event(
        "SITE_CONNECTORS_LISTED",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"count={len(data)}",
    )
    return {"connectors": data}


@sites_router.get("/site-health")
def site_health_all(user: dict = Depends(require_role("admin", "owner"))):
    t0 = time.monotonic()
    results = _health_service.check_all()
    duration_ms = int((time.monotonic() - t0) * 1000)
    payload = [r.to_dict() for r in results]
    log_event(
        "SITE_HEALTH_CHECK",
        task_id="-",
        actor=user["actor"],
        role=user["role"],
        decision="ok",
        note=f"scope=all | count={len(payload)} | duration_ms={duration_ms}",
    )
    return {"count": len(payload), "duration_ms": duration_ms, "results": payload}


@sites_router.get("/site-health/{site_name}")
def site_health_one(
    site_name: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    result = _health_service.check_one(site_name)
    if result is None:
        log_event(
            "SITE_HEALTH_CHECK",
            task_id="-",
            target=site_name,
            actor=user["actor"],
            role=user["role"],
            decision="not_found",
        )
        raise HTTPException(status_code=404, detail=f"connector 없음: {site_name}")

    log_event(
        "SITE_HEALTH_CHECK",
        task_id="-",
        target=site_name,
        actor=user["actor"],
        role=user["role"],
        decision=result.state,
        note=f"latency_ms={result.latency_ms}",
    )
    return result.to_dict()


@sites_router.post("/site-tasks/dry-run")
def site_task_dry_run(
    body: SiteTaskDryRunBody,
    user: dict = Depends(require_role("operator", "admin", "owner")),
):
    conn = registry.get(body.target_site)
    if conn is None:
        log_event(
            "SITE_TASK_DRY_RUN",
            task_id=body.task_id,
            target=body.target_site,
            action_type=body.action,
            actor=user["actor"],
            role=user["role"],
            decision="connector_not_found",
        )
        raise HTTPException(status_code=404, detail=f"connector 없음: {body.target_site}")

    task = SiteTask(
        task_id=body.task_id,
        target_site=body.target_site,
        action=body.action,
        params=body.params,
        risk_level=body.risk_level,
        requires_approval=body.requires_approval,
        execution_mode="dry_run",  # 이 엔드포인트는 dry_run 으로 고정
        requested_by=user["actor"],
        actor_role=user["role"],
    )

    t0 = time.monotonic()
    result = conn.dry_run(task)
    duration_ms = int((time.monotonic() - t0) * 1000)
    result.duration_ms = duration_ms

    log_event(
        "SITE_TASK_DRY_RUN",
        task_id=task.task_id,
        target=task.target_site,
        action_type=task.action,
        actor=user["actor"],
        role=user["role"],
        decision=result.status,
        note=(
            f"connector={conn.name} | duration_ms={duration_ms} "
            + (f"| error={result.error_code}" if result.error_code else "")
        ).strip(" |"),
    )

    # 지원하지 않는 action 은 HTTP 400 으로 명확히 돌려준다.
    if result.status == "unsupported_action":
        raise HTTPException(status_code=400, detail=result.to_dict())
    return result.to_dict()


__all__ = ["sites_router"]
