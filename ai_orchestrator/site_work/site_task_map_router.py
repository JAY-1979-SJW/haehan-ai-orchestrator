"""사이트 업무 지도 라우터 (L8) — HTTP 처리만. 규칙은 services/site_task_map_service.

기준서: docs/specs/2026-10-03_site_task_map.md (M2)
  GET  /site-map/hosts                    — 저장된 지도 요약                       [AI 허용: sitemap.list]
  GET  /site-map/{host}/lookup?q&limit    — 키워드로 업무 후보·절차 조회            [AI 허용: sitemap.lookup]
  GET  /site-map/{host}                   — 지도 전체(관리자 화면용)
  GET  /site-map/{host}/history           — 보존 중인 지도 버전 목록(map_rev·지문·시각)
  GET  /site-map/{host}/candidates        — '이 사이트에서 할 수 있는 일' 목록(never 는 자동 실행 불가로 표시)
  POST /site-map/{host}/spec              — 업무 명세 초안 생성 + 실행 계획(드라이런, 실행 없음). never 는 거부
  GET  /site-map/{host}/spec?task_key=    — 저장된 업무 명세·계획
  GET  /site-map/{host}/diff?from&to      — 두 지도 버전의 구조 차이(to 생략 = 현재)
  POST /site-map/{host}/classify          — 사람이 이름·목적·분류 확정(위험 등급 변경 불가)
  POST /site-map/{host}/outcome           — 실행 결과 기록(verified/stale)
  POST /site-map/{host}/run               — 저장된 조회(read) 업무를 지도 절차대로 실행                [AI 허용: sitemap.run]
  POST /site-map/explore/requests         — 탐색 요청 생성(승인 대기, 실행 안 함)    [AI 허용: sitemap.explore_request]
  GET  /site-map/explore/requests[/{id}]  — 요청 목록·상태(카드가 조회)
  POST /site-map/explore/requests/{id}/approve · /cancel — 사람만(카드 버튼). 승인하면 읽기 전용 탐색이 백그라운드로 시작

AI 가 쓸 수 있는 것은 읽기 2개 + 탐색 요청 생성 + 조회(read) 업무 실행(서버가 위험 등급을 강제)뿐 — 승인·취소·확정·결과 기록은 허용 목록에 없다. 모든 엔드포인트는 관리자 인증.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel

from ai_orchestrator.site_work import site_task_map_explore_service as explore
from ai_orchestrator.site_work import site_task_map_service as service
from ai_orchestrator.site_work import site_task_spec_service as spec_service
from tools.gates.auth import require_role

# 실행기(브라우저)는 이 모듈이 아니라 조합 루트(routers/registry.py)가 연결한다 — site_work 는 scripts.explorer 를 모른다

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


class ExploreBody(BaseModel):
    start_url: str
    depth: int | None = None
    max_pages: int | None = None
    reason: str = ""


class RunBody(BaseModel):
    task_id: str
    params: dict[str, str] = {}
    map_rev: int | None = None  # 기준으로 삼은 지도 버전(생략하면 현재 지도) — 어긋나면 map_changed 로 돌려준다


class SpecBody(BaseModel):
    task_key: str


class OutcomeBody(BaseModel):
    task_id: str
    ok: bool


@site_task_map_router.get("/hosts")
def list_hosts(_: dict = _ADMIN):
    return {"items": service.list_hosts()}


def _user(claims: dict) -> str:
    return str(claims.get("actor") or claims.get("username") or "admin")


def _rid():
    return PathParam(..., pattern=r"^[0-9a-f]{32}$")


@site_task_map_router.post("/explore/requests")
def create_explore(body: ExploreBody, claims: dict = _ADMIN):
    try:
        return explore.create_request(body.model_dump(exclude_none=True), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/explore/requests")
def list_explore(status: str | None = None, _: dict = _ADMIN):
    try:
        return {"items": explore.list_requests(status)}
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/explore/requests/{request_id}")
def get_explore(request_id: str = _rid(), _: dict = _ADMIN):
    try:
        return explore.get_request(request_id)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/explore/requests/{request_id}/approve")
def approve_explore(request_id: str = _rid(), claims: dict = _ADMIN):
    try:
        return explore.approve_request(request_id, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/explore/requests/{request_id}/cancel")
def cancel_explore(request_id: str = _rid(), claims: dict = _ADMIN):
    try:
        return explore.cancel_request(request_id, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}/lookup")
def lookup(q: str = "", limit: int = 5, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.lookup(host, q, limit=limit)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}/candidates")
def candidates(host: str = _host(), _: dict = _ADMIN):
    try:
        return spec_service.candidates(host)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/{host}/spec")
def create_spec(body: SpecBody, host: str = _host(), _: dict = _ADMIN):
    try:
        return spec_service.create_spec(host, body.task_key)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}/spec")
def get_spec(task_key: str = Query(..., min_length=1, max_length=200), host: str = _host(), _: dict = _ADMIN):
    try:
        return spec_service.get_spec(host, task_key)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}/history")
def map_history(host: str = _host(), _: dict = _ADMIN):
    try:
        return service.history(host)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.get("/{host}/diff")
def map_diff(rev_from: int = Query(..., alias="from", ge=1), rev_to: int | None = Query(None, alias="to", ge=1), host: str = _host(), _: dict = _ADMIN):
    try:
        return service.diff(host, rev_from, rev_to)
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


@site_task_map_router.post("/{host}/run")
def run_task(body: RunBody, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.run_task(host, body.task_id, body.params, map_rev=body.map_rev)
    except ValueError as e:
        raise _bad(e) from e


@site_task_map_router.post("/{host}/outcome")
def outcome(body: OutcomeBody, host: str = _host(), _: dict = _ADMIN):
    try:
        return service.record_outcome(host, body.task_id, ok=body.ok)
    except ValueError as e:
        raise _bad(e) from e
