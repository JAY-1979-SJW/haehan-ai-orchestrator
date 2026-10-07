"""Cleanup helpers for smoke-test agent and task removal."""

from __future__ import annotations

from .agent import get_agent_status
from .common import _agents, _lock, _save_agents_to_disk, _tasks


def get_agent_cleanup_preview(agent_id: str) -> dict:
    """cleanup 판정을 위한 preview 정보 반환.

    Response:
    {
        "agent_id": str,
        "eligible": bool,
        "reason": str,
        "task_count": int,
        "task_status_counts": {...}
    }
    """
    from ..policy.cleanup_policy import validate_cleanup_request

    with _lock:
        agent = _agents.get(agent_id)
        if agent is None:
            return {
                "agent_id": agent_id,
                "eligible": False,
                "reason": "agent_not_found",
                "task_count": 0,
            }

        agent_tasks = [t for t in _tasks.values() if t.agent_id == agent_id]
        task_statuses = [t.status for t in agent_tasks]

        policy = validate_cleanup_request(
            agent_id=agent_id,
            host=agent.host,
            label="",
            agent_status=get_agent_status(agent_id),
            task_statuses=task_statuses,
            dry_run=True,
            force=False,
            confirm=None,
            smoke_test=agent.smoke_test,
        )

        return {
            "agent_id": agent_id,
            "eligible": policy.eligible,
            "reason": policy.reason,
            "task_count": policy.task_count,
            "task_status_counts": policy.task_status_counts or {},
        }


def cleanup_agent_and_tasks(
    agent_id: str,
    *,
    dry_run: bool = True,
    force: bool = False,
    confirm: str | None = None,
    actor: str = "",
) -> dict:
    """cleanup agent와 task 정리.

    Policy:
    - smoke-test agent만 cleanup 대상
    - offline agent만 cleanup 대상
    - pending/running task 있으면 거부
    - dry_run=true: preview만 반환, 실제 삭제 안 함
    - dry_run=false: force=true + confirm 정확 일치 필수
    """
    from ..policy.cleanup_policy import validate_cleanup_request

    with _lock:
        agent = _agents.get(agent_id)
        if agent is None:
            return {
                "agent_id": agent_id,
                "dry_run": dry_run,
                "eligible": False,
                "reason": "agent_not_found",
                "status": "error",
                "deleted": False,
                "task_count": 0,
            }

        agent_tasks = [t for t in _tasks.values() if t.agent_id == agent_id]
        task_statuses = [t.status for t in agent_tasks]

        policy = validate_cleanup_request(
            agent_id=agent_id,
            host=agent.host,
            label="",
            agent_status=get_agent_status(agent_id),
            task_statuses=task_statuses,
            dry_run=dry_run,
            force=force,
            confirm=confirm,
            smoke_test=agent.smoke_test,
        )

        if dry_run or not policy.eligible:
            return {
                "agent_id": agent_id,
                "dry_run": dry_run,
                "eligible": policy.eligible,
                "reason": policy.reason,
                "status": "preview" if policy.eligible else "error",
                "deleted": False,
                "task_count": policy.task_count,
                "task_status_counts": policy.task_status_counts or {},
            }

        del _agents[agent_id]
        tasks_deleted = 0
        for task_id in list(_tasks.keys()):
            if _tasks[task_id].agent_id == agent_id:
                del _tasks[task_id]
                tasks_deleted += 1

    # 2026-09-29 pre-push AI 리뷰 지적 반영: _save_agents_to_disk()는 자체적으로 _lock을
    # 잡는다(재진입 불가 threading.Lock) — 위 with _lock 블록을 벗어난 뒤에 불러야 교착이
    # 안 생긴다. 삭제된 에이전트가 재시작 후 되살아나지 않게 반영.
    _save_agents_to_disk()

    return {
        "agent_id": agent_id,
        "dry_run": dry_run,
        "eligible": policy.eligible,
        "reason": policy.reason,
        "status": "cleaned",
        "deleted": True,
        "task_count": policy.task_count,
        "tasks_deleted": tasks_deleted,
    }


__all__ = ["cleanup_agent_and_tasks", "get_agent_cleanup_preview"]
