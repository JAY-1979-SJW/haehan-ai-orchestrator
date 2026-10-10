"""개발자 등록 승인 게이트 조회 API (read-only, admin/owner 전용).

GET /api/v1/dev-reg/approvals/pending      — 승인 대기 목록
GET /api/v1/dev-reg/approvals/history      — 이력(status/provider 필터, 페이지네이션, limit 상한 500)
GET /api/v1/dev-reg/approvals/{task_id}    — 단건 상세(없으면 404)

민감 필드(approval_token_hash, screenshot 절대경로)는 gates.dev_reg_approval 의 `_safe_dict` 가 제외한다.
커밋 3c155f55(hotfix, web-task route 제거) 때 router.py 에서 함께 빠졌던 3개 조회 엔드포인트를 그대로 복원한 것이다 —
web-task 자체는 949413df 로 이미 다시 켜져 있었다.

레이어: L8 Server API(router) — HTTP 처리만, 조회 로직은 gates.dev_reg_approval 에 있다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ai_orchestrator.dev_reg import dev_reg_approval as _dra
from tools.gates.auth import require_role

dev_reg_approval_read_router = APIRouter(prefix="/dev-reg/approvals", tags=["dev-reg-approvals"])


@dev_reg_approval_read_router.get("/pending")
def get_pending_approvals(user: dict = Depends(require_role("admin", "owner"))):
    return _dra.list_pending()


@dev_reg_approval_read_router.get("/history")
def get_approval_history(
    status: str | None = None,
    provider: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_role("admin", "owner")),
):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return _dra.list_history(status=status, provider=provider, limit=limit, offset=offset)


@dev_reg_approval_read_router.get("/{task_id}")
def get_approval_detail(task_id: str, user: dict = Depends(require_role("admin", "owner"))):
    rec = _dra.get_detail(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"task 없음: {task_id}")
    return rec
