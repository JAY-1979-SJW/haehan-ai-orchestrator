"""local_agent 정리(cleanup) 라우트군 — smoke-test agent/code 정리.

leaf 서브라우터. 컴포지션 루트(local_agent_router)가 include_router 로 관리.
[docs/module_separation_standard.md]
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..registry import facade as _reg
from ...audit.audit_logger import log_event
from tools.gates.auth import require_role

cleanup_router = APIRouter()


class AgentCleanupRequest(BaseModel):
    """agent cleanup 요청."""

    dry_run: bool = True
    force: bool = False
    confirm: str | None = None


@cleanup_router.post("/{agent_id}/cleanup")
def cleanup_local_agent(
    agent_id: str,
    body: AgentCleanupRequest,
    user: dict = Depends(require_role("admin", "owner")),
):
    """smoke-test agent cleanup endpoint.

    dry_run=true (기본): preview만 반환, 실제 삭제 안 함
    force=true + confirm 정확 일치: 실제 cleanup 수행

    Response:
    {
        "agent_id": str,
        "dry_run": bool,
        "eligible": bool,
        "reason": str,
        "status": "preview" | "cleaned" | "error",
        "deleted": bool,
        "task_count": int
    }
    """
    actor = user.get("name", "system") if user else "system"

    result = _reg.cleanup_agent_and_tasks(
        agent_id,
        dry_run=body.dry_run,
        force=body.force,
        confirm=body.confirm,
        actor=actor,
    )

    # 실제 cleanup 수행 시 audit log 기록
    if result.get("deleted"):
        log_event(
            "LOCAL_AGENT_CLEANUP",
            agent_id,
            actor=actor,
            role=user.get("role", "") if user else "",
            note=(
                f"status=cleanup_success"
                f" task_count={result.get('task_count', 0)}"
                f" tasks_deleted={result.get('tasks_deleted', 0)}"
            ),
        )

    return result
