"""사이트 업무 지도 라우터 (L8) — HTTP 처리만. 규칙은 services/site_task_map_service.

기준서: docs/specs/2026-10-03_site_task_map.md (M2)
  GET  /site-map/hosts                    — 저장된 지도 요약                       [AI 허용: sitemap.list]
  GET  /site-map/{host}/lookup?q&limit    — 키워드로 업무 후보·절차 조회            [AI 허용: sitemap.lookup]
  GET  /site-map/{host}                   — 지도 전체(관리자 화면용)
  POST /site-map/{host}/classify          — 사람이 이름·목적·분류 확정(위험 등급 변경 불가)
  POST /site-map/{host}/outcome           — 실행 결과 기록(verified/stale)

AI 가 쓸 수 있는 것은 위 두 개(읽기)뿐 — 확정·결과 기록은 허용 목록에 없다. 모든 엔드포인트는 관리자 인증.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from ai_orchestrator.gates.auth import require_role
from ai_orchestrator.services import site_task_map_service as service

site_task_map_router = APIRouter(prefix="/site-map", tags=["site-map"])
_ADMIN = Depends(require_role("admin", "owner"))


def _host():
    """경로의 호스트 이름. 공유 객체를 쓰면 FastAPI 가 첫 이름으로 고정하므로 매번 새로 만든다."""
    return PathParam(..., pattern=r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def _bad(e: ValueError) -> HTTPException:
    status = 404 if "찾을 수 없" in str(e) or "지도가 없" in str(e) else 400
    return HTTPException(status_code=status, detail=str(e))


class ClassifyBody(BaseModel):
    task_id: str
    name: str | None = None
    purpose: str | None = None
    category: str | None = None


class OutcomeBody(BaseModel):
    task_id: str
    ok: bool


@site_task_map_router.get("/hosts")
def list_hosts(_: dict = _ADMIN):
    return {"items": service.list_hosts()}


@site_task_map_router.get("/{host}/lookup")
def lookup(q: str = "", limit: int = 5, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.lookup(host, q, limit=limit)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}")
def get_map(host: str = _host(), _: dict = _ADMIN):
    try:
        return service.get_map(host)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/{host}/classify")
def classify(body: ClassifyBody, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.classify(host, body.task_id, name=body.name, purpose=body.purpose, category=body.category)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/{host}/outcome")
def outcome(body: OutcomeBody, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.record_outcome(host, body.task_id, ok=body.ok)
    except ValueError as e:
        raise _bad(e) from e
