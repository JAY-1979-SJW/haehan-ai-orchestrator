"""사용자 예약 작업 라우터 (L8).

기준서: docs/specs/2026-10-01_user_scheduled_jobs.md
  GET    /scheduled-jobs              — 예약 목록
  GET    /scheduled-jobs/actions      — 예약 가능한 작업 목록(설정 항목 포함)
  POST   /scheduled-jobs              — 예약 만들기
  POST   /scheduled-jobs/{id}/update  — 이름·설정·반복 수정 (PATCH 는 CORS 에서 허용되지 않아 POST)
  POST   /scheduled-jobs/{id}/pause | resume | run-now
  DELETE /scheduled-jobs/{id}
  GET    /scheduled-jobs/{id}/runs    — 실행 기록
  GET    /scheduled-jobs/approvals    — 승인 대기 중인 회차(발행·전송 등)
  POST   /scheduled-jobs/runs/{run_id}/approve | reject — 회차마다 승인·거부(승인하면 바로 실행)

SQLite·브라우저는 블로킹이라 엔드포인트를 `def` 로 둔다(FastAPI 가 스레드풀에서 실행).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_orchestrator.scheduler import scheduled_job_service as service
from ai_orchestrator.scheduler import scheduled_job_store as store
from ai_orchestrator.services import scheduled_job_actions as actions
from tools.gates.auth import require_role

scheduled_job_router = APIRouter(prefix="/scheduled-jobs", tags=["scheduled-jobs"])

_ADMIN = Depends(require_role("admin", "owner"))


class JobCreate(BaseModel):
    name: str
    action: str
    params: dict[str, Any] = {}
    recurrence: dict[str, Any]


class JobUpdate(BaseModel):
    name: str
    params: dict[str, Any] = {}
    recurrence: dict[str, Any]


def _bad_request(e: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="예약 작업을 찾을 수 없습니다")


@scheduled_job_router.get("")
def list_jobs(_: dict = _ADMIN):
    labels = {a["key"]: a["label"] for a in actions.catalog()}
    jobs = [{**j, "action_label": labels.get(j["action"], j["action"])} for j in store.list_jobs()]
    return {"jobs": jobs}


def _actor(user: dict) -> str:
    return str(user.get("actor") or user.get("email") or "unknown")


@scheduled_job_router.get("/approvals")
def list_approvals(_: dict = _ADMIN):
    return {"approvals": service.pending_approvals()}


@scheduled_job_router.post("/runs/{run_id}/approve")
def approve_run(run_id: str, user: dict = _ADMIN):
    try:
        return service.approve(run_id, _actor(user))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@scheduled_job_router.post("/runs/{run_id}/reject")
def reject_run(run_id: str, user: dict = _ADMIN):
    try:
        return service.reject(run_id, _actor(user))
    except KeyError as e:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다") from e
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@scheduled_job_router.get("/actions")
def list_actions(_: dict = _ADMIN):
    return {"actions": actions.catalog()}


@scheduled_job_router.post("")
def create_job(body: JobCreate, user: dict = _ADMIN):
    try:
        return service.create(
            name=body.name,
            action=body.action,
            params=body.params,
            recurrence=body.recurrence,
            created_by=_actor(user),
        )
    except ValueError as e:
        raise _bad_request(e) from e


@scheduled_job_router.post("/{job_id}/update")
def update_job(job_id: str, body: JobUpdate, _: dict = _ADMIN):
    try:
        return service.update(job_id, name=body.name, params=body.params, recurrence=body.recurrence)
    except KeyError as e:
        raise _not_found() from e
    except ValueError as e:
        raise _bad_request(e) from e


@scheduled_job_router.post("/{job_id}/pause")
def pause_job(job_id: str, _: dict = _ADMIN):
    try:
        return service.pause(job_id)
    except KeyError as e:
        raise _not_found() from e


@scheduled_job_router.post("/{job_id}/resume")
def resume_job(job_id: str, _: dict = _ADMIN):
    try:
        return service.resume(job_id)
    except KeyError as e:
        raise _not_found() from e
    except ValueError as e:
        raise _bad_request(e) from e


@scheduled_job_router.post("/{job_id}/run-now")
def run_job_now(job_id: str, _: dict = _ADMIN):
    """지금 한 번 실행한다. 브라우저 작업은 수 분 걸릴 수 있다."""
    try:
        return service.run_now(job_id)
    except KeyError as e:
        raise _not_found() from e


@scheduled_job_router.delete("/{job_id}")
def delete_job(job_id: str, _: dict = _ADMIN):
    if not store.delete_job(job_id):
        raise _not_found()
    return {"ok": True}


@scheduled_job_router.get("/{job_id}/runs")
def list_runs(job_id: str, limit: int = 20, _: dict = _ADMIN):
    if store.get_job(job_id) is None:
        raise _not_found()
    return {"runs": store.list_runs(job_id, limit=max(1, min(limit, 100)))}
