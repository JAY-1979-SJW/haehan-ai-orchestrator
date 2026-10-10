"""사이트 등록(온보딩) 라우터 (L8) — HTTP 처리만. 규칙은 services/site_onboarding_service.

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)
  GET   /site-registry                    — 등록 사이트 목록(상태·정책·지도 요약)            [AI 허용: sites.list]
  GET   /site-registry/{host}             — 등록 사이트 하나                                  [AI 허용: sites.get]
  POST  /site-registry                    — 사이트 등록 + 최초 탐색 시작(사람만 — 등록이 곧 승인)
  PATCH /site-registry/{host}/policy      — 탐색 정책 변경(사람만)
  POST  /site-registry/{host}/deregister  — 등록 해제(사람만, 지도는 보존)
  POST  /site-registry/{host}/preflight   — 사전 조사 실행(공식 API·robots·sitemap, 읽기 전용)
  GET   /site-registry/{host}/preflight   — 마지막 사전 조사 결과

경로는 `/site-map/*` 와 분리했다: `/site-map/{host}` 가 모든 한 단계 경로를 호스트로 받으므로 같은 접두사를 쓰면 라우트가 모호해진다.
AI 는 읽기 2개만 쓴다 — 등록·정책·해제는 AI 허용 목록에 없다(시험으로 고정).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from ai_orchestrator.site_work import site_onboarding_service as service
from ai_orchestrator.site_work import site_preflight_service as preflight
from tools.gates.auth import require_role

site_onboarding_router = APIRouter(prefix="/site-registry", tags=["site-registry"])
_ADMIN = Depends(require_role("admin", "owner"))
# 사전 조사 실행기(브라우저 없음, robots·sitemap 단순 GET)는 조합 루트(routers/registry.py)가 연결한다


def _host():
    """경로의 호스트 이름(공유 객체를 쓰면 FastAPI 가 첫 이름으로 고정하므로 매번 새로 만든다)."""
    return PathParam(..., pattern=r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def _user(claims: dict) -> str:
    return str(claims.get("actor") or claims.get("username") or "admin")


def _bad(e: ValueError) -> HTTPException:
    text = str(e)
    status = 404 if "찾을 수 없" in text else 409 if "이미 등록" in text else 400
    return HTTPException(status_code=status, detail=text)


class PolicyBody(BaseModel):
    auto_explore: str | None = None
    daily_explore_max: int | None = None
    max_pages: int | None = None


class RegisterBody(BaseModel):
    host: str
    start_url: str | None = None
    depth: int | None = None
    auth: str | None = None
    policy: PolicyBody | None = None


@site_onboarding_router.get("")
def list_sites(_: dict = _ADMIN):
    return {"items": service.list_sites()}


@site_onboarding_router.post("")
def register_site(body: RegisterBody, claims: dict = _ADMIN):
    raw = body.model_dump(exclude_none=True)
    try:
        return service.register(raw, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_onboarding_router.get("/{host}")
def get_site(host: str = _host(), _: dict = _ADMIN):
    try:
        return service.get_site(host)
    except ValueError as e:
        raise _bad(e) from e


@site_onboarding_router.patch("/{host}/policy")
def update_policy(body: PolicyBody, host: str = _host(), claims: dict = _ADMIN):
    try:
        return service.set_policy(host, body.model_dump(exclude_none=True), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_onboarding_router.post("/{host}/deregister")
def deregister_site(host: str = _host(), claims: dict = _ADMIN):
    try:
        return service.deregister(host, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@site_onboarding_router.post("/{host}/preflight")
def run_preflight(host: str = _host(), _: dict = _ADMIN):
    try:
        return preflight.run(host)
    except ValueError as e:
        raise _bad(e) from e


@site_onboarding_router.get("/{host}/preflight")
def get_preflight(host: str = _host(), _: dict = _ADMIN):
    try:
        found = preflight.latest(host)
    except ValueError as e:
        raise _bad(e) from e
    if found is None:
        raise HTTPException(status_code=404, detail="사전 조사 결과가 없습니다")
    return found
