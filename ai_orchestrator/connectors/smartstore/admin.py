"""라이선스 관리 Admin API (운영자 전용)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tools.gates.auth import require_role

from .agent_ws import get_connected_agents
from .license import issue, list_all, revoke, verify

router = APIRouter()


class IssueRequest(BaseModel):
    name: str
    email: str
    plan: str = "basic"
    expire_days: int = 365


@router.post("/admin/licenses/issue")
def api_issue(body: IssueRequest, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """라이선스 발급."""
    rec = issue(body.name, body.email, body.plan, body.expire_days)
    return {"ok": True, "license": rec}


@router.delete("/admin/licenses/{key}")
def api_revoke(key: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """라이선스 취소."""
    ok = revoke(key)
    return {"ok": ok}


@router.get("/admin/licenses")
def api_list(user: dict = Depends(require_role("admin", "owner"))) -> dict:
    """전체 라이선스 목록."""
    licenses = list_all()
    connected = set(get_connected_agents())
    for lic in licenses:
        lic["online"] = lic["key"] in connected
    return {"ok": True, "licenses": licenses, "total": len(licenses), "online": len(connected)}


@router.get("/admin/licenses/{key}/verify")
def api_verify(key: str, user: dict = Depends(require_role("admin", "owner"))) -> dict:
    ok, rec, reason = verify(key)
    return {"ok": ok, "reason": reason, "record": rec}


@router.get("/licenses/{key}/verify")
def api_verify_public(key: str) -> dict:
    """라이선스 검증 (인증 불필요 — 클라이언트 앱 전용)."""
    ok, rec, reason = verify(key)
    safe = {"name": rec["name"], "plan": rec["plan"], "expires_at": rec["expires_at"]} if rec else None
    return {"ok": ok, "reason": reason, "record": safe}
