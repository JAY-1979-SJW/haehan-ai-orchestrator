"""네이버 메일 순차 대량 발송 라우터 (L8) — HTTP 처리만. 업무 흐름은 connectors/naver_mail/bulk_service.

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md
  GET  /mail-bulk/authorizations                  — 승인서 목록(주소 마스킹)
  POST /mail-bulk/authorizations                  — 승인서 만들기(미승인, 수정 불가)
  GET  /mail-bulk/authorizations/{id}             — 승인서 1개 + 진행 상황
  POST /mail-bulk/authorizations/{id}/self-test   {to}      — 본인 주소 시험 발송 1통(실전송 승인의 선행 조건)
  POST /mail-bulk/authorizations/{id}/approve     {live}    — 승인(관리자)
  POST /mail-bulk/authorizations/{id}/revoke      — 취소(되돌릴 수 없음)
  POST /mail-bulk/authorizations/{id}/pause · /resume
  POST /mail-bulk/authorizations/{id}/run         — 지금 차례 발송 시작(백그라운드)
  GET  /mail-bulk/authorizations/{id}/log         — 발송 이력(주소 마스킹)
  POST /mail-bulk/import   {path}                 — 엑셀·CSV 주소록 읽기(허용 폴더 안의 파일만)
  POST /mail-bulk/opt-out  {email, reason}        — 수신거부 등록
  POST /mail-bulk/kill-switch {on}                — 전체 정지 켜기/끄기

**AI 허용 아님**: `mcp_server.API_REGISTRY` 에 넣지 않는다(테스트가 고정). 모든 엔드포인트는 관리자 인증.
SMTP·sqlite 는 블로킹이라 엔드포인트를 `def` 로 둔다(FastAPI 가 스레드풀에서 실행 — 공식 문서 권장).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from ai_orchestrator.connectors.naver_mail import bulk_service as service
from tools.gates.auth import require_role

naver_mail_bulk_router = APIRouter(prefix="/mail-bulk", tags=["mail-bulk"])
_ADMIN = Depends(require_role("admin", "owner"))
_ID = PathParam(..., pattern=r"^[0-9a-f]{32}$")


def _user(claims: dict) -> str:
    return str(claims.get("actor") or claims.get("username") or "admin")


def _bad(e: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


class CreateBody(BaseModel):
    account: str
    name: str = ""
    kind: str
    subject: str
    body: str
    recipients: list[dict[str, Any]]
    attachment_paths: list[str] = Field(default_factory=list)
    interval_sec: int | None = None
    max_per_run: int | None = None
    max_per_day: int | None = None
    max_total: int | None = None
    allowed_start: str | None = None
    allowed_end: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None


class SelfTestBody(BaseModel):
    to: str


class ApproveBody(BaseModel):
    live: bool = False


class ImportBody(BaseModel):
    path: str


class OptOutBody(BaseModel):
    email: str
    reason: str = ""


class KillBody(BaseModel):
    on: bool


@naver_mail_bulk_router.get("/authorizations")
def list_authorizations(_: dict = _ADMIN):
    return {"items": service.list_all()}


@naver_mail_bulk_router.post("/authorizations")
def create_authorization(body: CreateBody, claims: dict = _ADMIN):
    try:
        return service.create(body.model_dump(), user=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.get("/authorizations/{auth_id}")
def get_authorization(auth_id: str = _ID, _: dict = _ADMIN):
    try:
        return {"authorization": service.get(auth_id), "status": service.status(auth_id)}
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/self-test")
def self_test(body: SelfTestBody, auth_id: str = _ID, _: dict = _ADMIN):
    try:
        return service.send_self_test(auth_id, body.to)
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/approve")
def approve(body: ApproveBody, auth_id: str = _ID, claims: dict = _ADMIN):
    try:
        return service.approve(auth_id, user=_user(claims), live=body.live)
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/revoke")
def revoke(auth_id: str = _ID, claims: dict = _ADMIN):
    try:
        return service.revoke(auth_id, user=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/pause")
def pause(auth_id: str = _ID, _: dict = _ADMIN):
    try:
        return service.pause(auth_id)
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/resume")
def resume(auth_id: str = _ID, _: dict = _ADMIN):
    try:
        return service.resume(auth_id)
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/authorizations/{auth_id}/run")
def run_now(auth_id: str = _ID, _: dict = _ADMIN):
    try:
        return service.start(auth_id)
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.get("/authorizations/{auth_id}/log")
def send_log(auth_id: str = _ID, _: dict = _ADMIN):
    return {"items": service.send_log(auth_id)}


@naver_mail_bulk_router.post("/import")
def import_recipients(body: ImportBody, _: dict = _ADMIN):
    try:
        recipients, stats = service.import_recipients(body.path)
    except ValueError as e:
        raise _bad(e) from e
    return {"recipients": recipients, "stats": stats}


@naver_mail_bulk_router.post("/opt-out")
def opt_out(body: OptOutBody, claims: dict = _ADMIN):
    try:
        return {"email": service.add_opt_out(body.email, reason=body.reason, user=_user(claims))}
    except ValueError as e:
        raise _bad(e) from e


@naver_mail_bulk_router.post("/kill-switch")
def kill_switch(body: KillBody, claims: dict = _ADMIN):
    return service.set_kill_switch(body.on, user=_user(claims))
