"""
Action Approval/Handoff API 라우터

엔드포인트:
  POST /api/v1/actions/prepare  — action 실행 준비 (승인 요청 / handoff 생성)
  POST /api/v1/actions/evidence — evidence safe field 수신 저장

역할:
  - 요청 body 검증 (Pydantic)
  - api_prepare_action / api_receive_evidence 호출 (정책 판단 재구현 금지)
  - 결과를 그대로 반환

보안:
  - 라우터에서 직접 policy/risk/approval 판단 금지
  - raw params 저장 금지
  - 민감 필드 응답 금지
  - 서버에서 외부 브라우저 실행 금지
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai_orchestrator.server.action_task_api import (
    api_prepare_action,
    api_receive_evidence,
)
from tools.gates.auth import require_role

logger = logging.getLogger(__name__)

action_router = APIRouter(prefix="/actions", tags=["actions"])

# ── 금지 응답 필드 (안전 확인용) ─────────────────────────────────────────────

_FORBIDDEN_RESPONSE_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "otp",
        "cert_password",
        "certificate_password",
        "cookie",
        "cookies",
        "session",
        "storage_state",
        "private_key",
        "npki",
        "auth_header",
        "access_token",
        "refresh_token",
    }
)


def _strip_forbidden(data: dict[str, Any]) -> dict[str, Any]:
    """응답 dict에서 금지 필드를 제거한다."""
    return {k: v for k, v in data.items() if k not in _FORBIDDEN_RESPONSE_FIELDS}


# ── Pydantic models ───────────────────────────────────────────────────────────


class PrepareRequest(BaseModel):
    action_name: str
    params: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "anonymous"
    user_intent_summary: str = ""
    site_context: str = ""
    target_context: str = ""
    approval_token: str | None = None
    dry_run: bool = True


class EvidenceRequest(BaseModel):
    action_name: str
    approval_request_id: str = ""
    params_hash: str = ""
    result_status: str
    result_fields_safe: dict[str, Any] = Field(default_factory=dict)
    evidence_files_ref: list[str] = Field(default_factory=list)
    local_agent_run_id: str = ""
    occurred_at: str = ""


# ── endpoints ─────────────────────────────────────────────────────────────────


@action_router.post("/prepare")
def prepare_action(
    body: PrepareRequest,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """
    action 실행 준비.

    정책 판단(risk/approval/params_hash)은 service layer에 위임한다.
    라우터에서 직접 판단 금지.
    """
    result = api_prepare_action(
        action_name=body.action_name,
        params=body.params,
        requested_by=body.requested_by or current_user.get("actor", "anonymous"),
        user_intent_summary=body.user_intent_summary,
        site_context=body.site_context,
        target_context=body.target_context,
        approval_token=body.approval_token,
        dry_run=body.dry_run,
    )
    return _strip_forbidden(result)


@action_router.post("/evidence")
def receive_evidence(
    body: EvidenceRequest,
    current_user: dict = Depends(require_role("operator", "admin", "owner")),
) -> dict[str, Any]:
    """
    local agent 실행 evidence 수신.

    forbidden field 포함 시 service layer에서 BLOCKED 반환.
    """
    result = api_receive_evidence(
        action_name=body.action_name,
        approval_request_id=body.approval_request_id,
        params_hash=body.params_hash,
        result_status=body.result_status,
        result_fields_safe=body.result_fields_safe,
        evidence_files_ref=body.evidence_files_ref,
        local_agent_run_id=body.local_agent_run_id,
        occurred_at=body.occurred_at,
    )
    return _strip_forbidden(result)
