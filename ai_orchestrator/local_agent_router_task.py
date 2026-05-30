"""local_agent 작업(task) 라우트군 — 조회(list/get) leaf 서브라우터.

컴포지션 루트(local_agent_router)가 include_router 로 관리.
(cancel/approve/reject 등 작업 처리 라우트는 후속 슬라이스에서 합류)
sibling leaf 는 직접 import 하지 않는다. [docs/module_separation_standard.md]
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_role
from . import local_agent_registry as _reg

task_router = APIRouter()


@task_router.get("/{agent_id}/tasks")
def list_local_agent_tasks(
    agent_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    if status is not None and status not in _reg.KNOWN_TASK_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={"error": "UNKNOWN_STATUS",
                    "message": f"알 수 없는 status: {status}"},
        )
    tasks = _reg.list_tasks_for_agent(agent_id, status=status, limit=limit)
    return {
        "agent_id": agent_id,
        "total": len(tasks),
        "tasks": [t.to_list_safe() for t in tasks],
    }


@task_router.get("/{agent_id}/tasks/{task_id}")
def get_local_agent_task(
    agent_id: str,
    task_id: str,
    user: dict = Depends(require_role("admin", "owner", "viewer")),
):
    task = _reg.get_task(agent_id, task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "TASK_NOT_FOUND",
                    "message": f"미등록 작업: {agent_id}/{task_id}"},
        )
    return task.to_safe()
