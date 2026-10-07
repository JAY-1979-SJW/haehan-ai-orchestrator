"""사람 승인 발급 API (R2d-2 P0c).

- 제안(`POST /approvals/requests`)과 조회는 로그인한 admin·owner·operator 가 할 수 있다. 제안은 승인을 만들지 않는다.
- 발급(`approve`·`reject`·`revoke`)은 `require_human_session` 을 통과한 사람 세션만 — Basic·MCP·viewer·operator·프록시 증명 없음은 거부.
- 이 라우터는 MCP `API_REGISTRY` 에 넣지 않는다(에이전트가 승인 경로를 알 수 없게). 계약 시험이 고정한다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..gates import human_approval as ha
from ..gates.auth import require_role
from ..gates.human_session import require_human_session

human_approval_router = APIRouter(prefix="/approvals", tags=["human-approvals"])

_PROPOSE_ROLES = ("admin", "owner", "operator")


class ProposeBody(BaseModel):
    op: str = Field(min_length=1, max_length=100)
    target: str | list[str]
    content: Any
    target_preview: str = ""
    schedule_job_id: str | None = None
    max_uses: int = Field(default=1, ge=1, le=1000)


class ApproveBody(BaseModel):
    ttl_seconds: int = Field(default=ha.DEFAULT_TTL_S, ge=60, le=7 * 24 * 3600)


def _conflict(exc: ha.ApprovalError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@human_approval_router.post("/requests")
def propose(body: ProposeBody, user: dict = Depends(require_role(*_PROPOSE_ROLES))) -> dict:
    try:
        rid = ha.request_approval(
            body.op,
            body.target,
            body.content,
            requested_by=str(user.get("actor", "")),
            target_preview=body.target_preview,
            schedule_job_id=body.schedule_job_id,
            max_uses=body.max_uses,
        )
    except ha.ApprovalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": rid, "status": ha.PENDING}


@human_approval_router.get("/pending")
def pending(_: dict = Depends(require_role(*_PROPOSE_ROLES))) -> dict:
    return {"items": ha.list_pending()}


@human_approval_router.get("/{request_id}")
def detail(request_id: str, _: dict = Depends(require_role(*_PROPOSE_ROLES))) -> dict:
    rec = ha.get_request(request_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="승인 요청이 없습니다")
    return rec


@human_approval_router.post("/{request_id}/approve")
def approve(request_id: str, body: ApproveBody | None = None, session: dict = Depends(require_human_session)) -> dict:
    try:
        return ha.approve(
            request_id,
            approved_by=session["actor"],
            approved_via=session["approved_via"],
            ttl_seconds=(body or ApproveBody()).ttl_seconds,
        )
    except ha.ApprovalError as exc:
        raise _conflict(exc) from exc


@human_approval_router.post("/{request_id}/reject")
def reject(request_id: str, session: dict = Depends(require_human_session)) -> dict:
    try:
        ha.reject(request_id, rejected_by=session["actor"])
    except ha.ApprovalError as exc:
        raise _conflict(exc) from exc
    return {"id": request_id, "status": ha.REJECTED}


@human_approval_router.post("/{request_id}/revoke")
def revoke(request_id: str, session: dict = Depends(require_human_session)) -> dict:
    try:
        ha.revoke(request_id, revoked_by=session["actor"])
    except ha.ApprovalError as exc:
        raise _conflict(exc) from exc
    return {"id": request_id, "status": ha.REVOKED}
