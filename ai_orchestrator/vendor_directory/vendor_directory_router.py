"""벤더 공식 API 목록 라우터 (L8) — HTTP 처리만. 규칙은 services/vendor_directory_service.

기준서: docs/specs/2026-10-04_ai_employee.md (E1)
  GET /vendors/lookup?q=  — 서비스·사이트 이름으로 공식 API 조회(읽기 전용)   [AI 허용: vendors.lookup]
관리자 인증. 목록 수정 API 는 없다(사람이 검토해 `configs/vendor_apis.json` 을 고친다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ai_orchestrator.vendor_directory import vendor_directory_service as service
from tools.gates.auth import require_role

vendor_directory_router = APIRouter(prefix="/vendors", tags=["vendors"])
_ADMIN = Depends(require_role("admin", "owner"))


@vendor_directory_router.get("/lookup")
def lookup(q: str = "", _: dict = _ADMIN):
    try:
        return service.lookup(q)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
