"""건설업 공무 업무판 라우터 (L8) — HTTP 처리만. 업무 흐름은 services/gongmu_service.

기준서: docs/specs/2026-10-02_construction_gongmu.md (G1)
  GET  /gongmu/summary                    — 지연·임박·기한 확인 필요 건수와 목록(배지용)
  GET  /gongmu/settings · PUT             — 금액 기준·임박 일수(수정하면 업무를 다시 계산)
  GET  /gongmu/catalog                    — 업무 기준표(근거 문구·필요 서류·법령 확인 표시)
  GET/POST /gongmu/sites · GET/PATCH /gongmu/sites/{id}
  POST /gongmu/sites/{id}/contracts       — 계약 등록 / POST /gongmu/contracts/{id}/changes — 변경 기록
  POST /gongmu/sites/{id}/generate        — 업무 다시 계산(없는 것만 추가)
  GET  /gongmu/tasks?site_id&status · GET /gongmu/tasks/{id}
  POST /gongmu/tasks/{id}/status · PATCH /gongmu/tasks/{id} · POST /gongmu/tasks/{id}/docs
  POST /gongmu/import/sites · /import/contracts  {path} — 허용 폴더 안의 엑셀·CSV
  GET  /gongmu/events                     — 변경 이력(추가만)

  POST/GET /gongmu/drafts · GET /gongmu/drafts/{id} — G2 AI 초안(승인 대기)
  POST /gongmu/drafts/{id}/confirm · /cancel        — 사람만(카드 버튼)

AI 허용(mcp_server)은 sites·tasks·tasks/{id}·drafts(POST/GET) 뿐 — 확정·취소 등 나머지는 허용 아님. 모든 엔드포인트는 관리자 인증.
sqlite·파일 읽기가 블로킹이라 엔드포인트를 `def` 로 둔다(FastAPI 가 스레드풀에서 실행 — 공식 문서 권장).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from ai_orchestrator.gongmu import gongmu_service as service
from tools.gates.auth import require_role

gongmu_router = APIRouter(prefix="/gongmu", tags=["gongmu"])
_ADMIN = Depends(require_role("admin", "owner"))


def _id():
    """경로 id(32자리 16진수). 공유 객체를 쓰면 FastAPI 가 첫 사용 이름으로 고정해 다른 이름의 경로가 깨지므로 매번 새로 만든다."""
    return PathParam(..., pattern=r"^[0-9a-f]{32}$")


def _user(claims: dict) -> str:
    return str(claims.get("actor") or claims.get("username") or "admin")


def _bad(e: ValueError) -> HTTPException:
    status = 404 if "찾을 수 없" in str(e) else 400
    return HTTPException(status_code=status, detail=str(e))


class SiteBody(BaseModel):
    name: str = ""
    client: str = ""
    location: str = ""
    start_date: str | None = None
    end_date: str | None = None
    role: str = "원도급"
    contract_amount: str | int | None = None
    manager: str = ""
    memo: str = ""


class SitePatch(BaseModel):
    name: str | None = None
    client: str | None = None
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    role: str | None = None
    contract_amount: str | int | None = None
    manager: str | None = None
    memo: str | None = None


class ContractBody(BaseModel):
    kind: str
    counterparty: str = ""
    amount: str | int | None = None
    contract_date: str | None = None
    memo: str = ""


class ChangeBody(BaseModel):
    date: str
    amount: str | int | None = None
    period_end: str | None = None
    memo: str = ""


class StatusBody(BaseModel):
    status: str


class TaskPatch(BaseModel):
    due_date: str | None = None
    assignee: str | None = None
    memo: str | None = None


class DocBody(BaseModel):
    doc_name: str
    ready: bool = False
    path: str = ""


class ImportBody(BaseModel):
    path: str


class DraftBody(BaseModel):
    kind: str
    title: str = ""
    body: str
    site_id: str | None = None
    task_id: str | None = None


class SettingsBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


@gongmu_router.get("/summary")
def summary(_: dict = _ADMIN):
    return service.summary()


@gongmu_router.get("/settings")
def get_settings(_: dict = _ADMIN):
    return {"settings": service.get_settings(), "disclaimer": service.DISCLAIMER}


@gongmu_router.put("/settings")
def put_settings(body: SettingsBody, claims: dict = _ADMIN):
    try:
        return service.update_settings(body.values, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/catalog")
def catalog(_: dict = _ADMIN):
    return {"items": service.list_catalog()}


@gongmu_router.get("/sites")
def list_sites(_: dict = _ADMIN):
    return {"items": service.list_sites()}


@gongmu_router.post("/sites")
def create_site(body: SiteBody, claims: dict = _ADMIN):
    try:
        return service.create_site(body.model_dump(), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/sites/{site_id}")
def get_site(site_id: str = _id(), _: dict = _ADMIN):
    try:
        return service.get_site(site_id)
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.patch("/sites/{site_id}")
def patch_site(body: SitePatch, site_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.update_site(site_id, body.model_dump(exclude_unset=True), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/sites/{site_id}/contracts")
def create_contract(body: ContractBody, site_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.create_contract(site_id, body.model_dump(), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/contracts/{contract_id}/changes")
def add_change(body: ChangeBody, contract_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.add_contract_change(contract_id, body.model_dump(), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/sites/{site_id}/generate")
def generate(site_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.generate_for_site(site_id, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/tasks")
def list_tasks(site_id: str | None = None, status: str | None = None, _: dict = _ADMIN):
    return {"items": service.list_tasks(site_id, status)}


@gongmu_router.get("/tasks/{task_id}")
def get_task(task_id: str = _id(), _: dict = _ADMIN):
    try:
        return service.get_task(task_id)
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/tasks/{task_id}/status")
def set_status(body: StatusBody, task_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.set_status(task_id, body.status, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.patch("/tasks/{task_id}")
def patch_task(body: TaskPatch, task_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.update_task(task_id, body.model_dump(exclude_unset=True), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/tasks/{task_id}/docs")
def set_doc(body: DocBody, task_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.set_doc(task_id, body.doc_name, ready=body.ready, path=body.path, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/import/sites")
def import_sites(body: ImportBody, claims: dict = _ADMIN):
    try:
        return service.import_sites(body.path, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/import/contracts")
def import_contracts(body: ImportBody, claims: dict = _ADMIN):
    try:
        return service.import_contracts(body.path, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/events")
def events(limit: int = 100, _: dict = _ADMIN):
    return {"items": service.list_events(limit)}


@gongmu_router.post("/drafts")
def create_draft(body: DraftBody, claims: dict = _ADMIN):
    try:
        return service.create_draft(body.model_dump(), actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/drafts")
def list_drafts(status: str | None = None, _: dict = _ADMIN):
    try:
        return {"items": service.list_drafts(status)}
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.get("/drafts/{draft_id}")
def get_draft(draft_id: str = _id(), _: dict = _ADMIN):
    try:
        return service.get_draft(draft_id)
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/drafts/{draft_id}/confirm")
def confirm_draft(draft_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.confirm_draft(draft_id, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e


@gongmu_router.post("/drafts/{draft_id}/cancel")
def cancel_draft(draft_id: str = _id(), claims: dict = _ADMIN):
    try:
        return service.cancel_draft(draft_id, actor=_user(claims))
    except ValueError as e:
        raise _bad(e) from e
