"""AI 에이전트 작업 분배 라우터 (L8) — HTTP 처리만. 업무 흐름은 services/agent_dispatch_service.

기준서: docs/specs/2026-10-02_app_agent_dispatch.md (P3)
  POST /ai-agent/dispatch                — 목표로 분배안 만들기(계획자 실행, 미승인 상태로 저장)
  GET  /ai-agent/dispatch                — 분배안 목록
  GET  /ai-agent/dispatch/{id}           — 분배안 1개(계획 결과 반영·진행 상황·최종 결과)
  POST /ai-agent/dispatch/{id}/approve   — 사람이 승인 → 정책이 허용한 만큼 동시 실행
  POST /ai-agent/dispatch/{id}/cancel    — 취소(실행 중 하위 작업도 취소 요청)

**AI 허용 아님**: `mcp_server.API_REGISTRY` 에 넣지 않는다(테스트가 고정). 모든 엔드포인트는 관리자 인증.
sqlite·큐 접근은 블로킹이라 엔드포인트를 `def` 로 둔다(FastAPI 가 스레드풀에서 실행).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from ai_orchestrator.agent_dispatch import agent_dispatch_runner as runner
from ai_orchestrator.agent_dispatch import agent_dispatch_service as service
from ai_orchestrator.agent_dispatch import agent_dispatch_store as store
from tools.gates.auth import require_role

agent_dispatch_router = APIRouter(prefix="/ai-agent/dispatch", tags=["ai-agent-dispatch"])
_ADMIN = Depends(require_role("admin", "owner"))
_ID = PathParam(..., pattern=r"^[0-9a-f]{32}$")


def resume_on_startup() -> bool:
    """서버가 다시 켜질 때, 승인된 채 끝나지 않은 분배안이 있으면 러너를 다시 띄운다. 재개했으면 True.

    server.py 가 workflows/ 를 직접 가져오면 루트 모듈↔workflows 순환이 생기므로, 이미 이 라우터를 가져오는
    server.py 가 이 함수를 거쳐 부른다(예약 작업 루프를 routers/ 에 둔 것과 같은 이유).
    """
    return runner.resume_running()


def _user(claims: dict) -> str:
    return str(claims.get("actor") or claims.get("username") or "admin")


def _bad(e: service.DispatchError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


class CreateBody(BaseModel):
    goal: str
    max_parallel: int | None = None


@agent_dispatch_router.post("")
def create(body: CreateBody, claims: dict = _ADMIN):
    try:
        return service.create_dispatch(body.goal, _user(claims), body.max_parallel)
    except service.DispatchError as e:
        raise _bad(e) from e


@agent_dispatch_router.get("")
def list_all(claims: dict = _ADMIN):
    return {"items": store.list_dispatches()}


@agent_dispatch_router.get("/{did}")
def get_one(did: str = _ID, claims: dict = _ADMIN):
    d = service.view(did)
    if d is None:
        raise HTTPException(status_code=404, detail="분배안을 찾을 수 없습니다")
    if d["status"] == store.RUNNING:
        runner.ensure_running()  # 서버 재시작 뒤 실행 중이던 분배안 이어서 진행
    return d


@agent_dispatch_router.post("/{did}/approve")
def approve(did: str = _ID, claims: dict = _ADMIN):
    try:
        result = service.approve(did, _user(claims))
    except service.DispatchError as e:
        raise _bad(e) from e
    runner.ensure_running()
    return result


@agent_dispatch_router.post("/{did}/cancel")
def cancel(did: str = _ID, claims: dict = _ADMIN):
    try:
        return service.cancel(did, _user(claims))
    except service.DispatchError as e:
        raise _bad(e) from e
