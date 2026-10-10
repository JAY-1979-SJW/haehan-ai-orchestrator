"""local_agent 사용자임장(USER_PRESENT) 라우트군 — status / statuses / dispatch.

leaf 서브라우터. 컴포지션 루트(local_agent_router)가 include_router 로 관리.
USER_PRESENT 상태 store/dispatcher 는 선택 의존(없으면 503).
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..registry import facade as _reg
from ...audit.audit_logger import log_event
from tools.gates.auth import require_role
from .up_queue import _enqueue_up_task  # 공유 leaf

try:
    from ..user_present_status_store import (
        get_user_present_status as _get_up_status,
    )
    from ..user_present_status_store import (
        list_user_present_statuses as _list_up_statuses,
    )

    _UP_STATUS_STORE_AVAILABLE = True
except ImportError:
    _UP_STATUS_STORE_AVAILABLE = False

try:
    from ..user_present_dispatcher import (
        build_user_present_dispatch_response,
    )

    _UP_DISPATCHER_AVAILABLE = True
except ImportError:
    _UP_DISPATCHER_AVAILABLE = False

user_present_router = APIRouter()


class UserPresentDispatchRequest(BaseModel):
    """USER_PRESENT_TASK dispatch 요청 body."""

    workflow_run_id: str
    workflow_id: str = ""
    tenant_id: str
    user_id: str
    site_id: str
    site_category: str = ""
    target_domain: str = ""
    target_url_redacted: str = ""
    target_url_hash: str = ""
    auth_method_label: str = ""
    selected_agent_id: str
    dryrun_result: dict = {}


@user_present_router.get("/user-present-status/{workflow_run_id}")
def get_user_present_status_record(
    workflow_run_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    """workflow_run_id 기준 USER_PRESENT_STATUS 수신 기록 조회."""
    if not _UP_STATUS_STORE_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "STATUS_STORE_UNAVAILABLE"})
    record = _get_up_status(workflow_run_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NOT_FOUND", "workflow_run_id": workflow_run_id},
        )
    return {"ok": True, "safe_to_execute": False, "record": record}


@user_present_router.get("/{agent_id}/user-present-statuses")
def list_agent_user_present_statuses(
    agent_id: str,
    user: dict = Depends(require_role("admin", "owner")),
):
    """agent_id 기준 USER_PRESENT_STATUS 수신 목록 조회."""
    if not _UP_STATUS_STORE_AVAILABLE:
        raise HTTPException(status_code=503, detail={"error": "STATUS_STORE_UNAVAILABLE"})
    records = _list_up_statuses(agent_id=agent_id)
    return {"ok": True, "safe_to_execute": False, "agent_id": agent_id, "records": records, "total": len(records)}


@user_present_router.post("/{agent_id}/user-present-dispatch")
def dispatch_user_present_task(
    agent_id: str,
    body: UserPresentDispatchRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """routing dry-run 결과가 USER_PRESENT_REQUIRED일 때 USER_PRESENT_TASK를 agent에 전송 예약.

    실제 WebSocket 송신은 다음 heartbeat/pull 시 수행.
    safe_to_execute=False 항상.
    """
    actor = user["actor"]
    role = user["role"]

    if _reg.get_agent(agent_id) is None:
        log_event(
            "LOCAL_AGENT_TASK_REJECTED",
            "local-agent",
            action_type="user_present_dispatch",
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} reason=AGENT_NOT_FOUND",
        )
        raise HTTPException(
            status_code=404,
            detail={"error": "AGENT_NOT_FOUND", "message": f"미등록 에이전트: {agent_id}"},
        )

    if not _UP_DISPATCHER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={"error": "DISPATCHER_UNAVAILABLE", "message": "dispatcher 모듈 없음"},
        )

    payload = {
        "workflow_run_id": body.workflow_run_id,
        "workflow_id": body.workflow_id,
        "tenant_id": body.tenant_id,
        "user_id": body.user_id,
        "site_id": body.site_id,
        "site_category": body.site_category,
        "target_domain": body.target_domain,
        "target_url_redacted": body.target_url_redacted,
        "target_url_hash": body.target_url_hash,
        "auth_method_label": body.auth_method_label,
        "selected_agent_id": body.selected_agent_id,
        "dryrun_result": body.dryrun_result,
    }

    result = build_user_present_dispatch_response(payload)
    if not result.get("ok"):
        log_event(
            "LOCAL_AGENT_TASK_REJECTED",
            "local-agent",
            action_type="user_present_dispatch",
            actor=actor,
            role=role,
            note=f"agent_id={agent_id} errors={result.get('errors', [])}",
        )
        raise HTTPException(
            status_code=400,
            detail={"error": "DISPATCH_VALIDATION_FAILED", "message": result.get("message_ko", "")},
        )

    task_message = result.get("task_message", {})
    task_message["safe_to_execute"] = False
    _enqueue_up_task(agent_id, task_message)

    log_event(
        "LOCAL_AGENT_USER_PRESENT_TASK_DISPATCHED",
        body.workflow_run_id,
        actor=actor,
        role=role,
        note=f"agent_id={agent_id} site_id={body.site_id}",
    )

    return {
        "ok": True,
        "dispatched": True,
        "workflow_run_id": body.workflow_run_id,
        "agent_id": agent_id,
        "dispatch_decision": result.get("dispatch_decision", ""),
        "safe_to_execute": False,
        "message_ko": result.get("message_ko", ""),
    }
