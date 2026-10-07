"""범용 업무 실행 핸들러 — 사용자 승인 후 local agent handoff 생성."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.agent_hub.action_registry import register_handler
from ai_orchestrator.agent_hub.business_action_profiles import (
    COMMON_FORBIDDEN_FIELDS,
    build_evidence_policy,
    get_profile,
)
from ai_orchestrator.agent_hub.policy.user_approval_gate import sanitize_params, verify_and_consume_token

ACTION_NAME = "business.execute_with_user_approval"


def _url_safe(url: str) -> str:
    """URL에서 query/fragment 제거 (scheme://host/path만 보존)."""
    if not url:
        return ""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _remove_forbidden_fields(data: dict[str, Any]) -> dict[str, Any]:
    """dict에서 forbidden field를 제거."""
    result = {}
    for key, val in data.items():
        key_lower = key.lower()
        if not any(f in key_lower for f in COMMON_FORBIDDEN_FIELDS):
            result[key] = val
    return result


def execute(**kwargs) -> dict[str, Any]:
    """
    범용 업무 실행 — 사용자 승인 후 local agent handoff 생성.

    입력:
    - page_url: 업무 수행 페이지 URL (필수)
    - submit_selector: 제출/실행 버튼 selector (필수)
    - business_profile: 업무 프로필 (필수, 6종 중 하나)
    - approval_token: 사용자 승인 토큰 (필수)
    - 기타 필드들 (프로필별 정보)

    출력:
    - verdict: EXECUTE_HANDOFF_READY 또는 ERROR/APPROVAL_REQUIRED/APPROVAL_REJECTED
    - approval_status: APPROVED_AND_CONSUMED 또는 INVALID
    - handoff_required: True
    - handoff_payload: local agent가 실행할 정보 (safe fields만)
    - evidence: 감사 증거
    """

    # 필수 필드 검증
    page_url = kwargs.get("page_url", "").strip()
    if not page_url:
        return {"ok": False, "verdict": "ERROR", "error": "page_url 필수"}

    submit_selector = kwargs.get("submit_selector", "").strip()
    if not submit_selector:
        return {"ok": False, "verdict": "ERROR", "error": "submit_selector 필수"}

    business_profile = kwargs.get("business_profile", "").strip()
    if not business_profile:
        return {"ok": False, "verdict": "ERROR", "error": "business_profile 필수"}

    profile = get_profile(business_profile)
    if not profile:
        available = (
            "bid_submission, erp_save, erp_submit_approval, document_submission, public_agency_upload, esign_request"
        )
        return {
            "ok": False,
            "verdict": "ERROR",
            "error": f"미지원 business_profile: {business_profile}. 지원: {available}",
        }

    # 승인 토큰 검증
    approval_token = kwargs.get("approval_token", "").strip()
    if not approval_token:
        return {
            "ok": False,
            "verdict": "APPROVAL_REQUIRED",
            "error": "approval_token 필수",
            "approval_status": "NOT_PROVIDED",
        }

    # 토큰 검증 및 소비
    sanitized_params = sanitize_params(kwargs)
    verify_result = verify_and_consume_token(approval_token, ACTION_NAME, sanitized_params)

    if not verify_result.get("ok"):
        return {
            "ok": False,
            "verdict": "APPROVAL_REJECTED",
            "approval_status": "INVALID",
            "error": verify_result.get("error", "토큰 검증 실패"),
        }

    # approval_request_id 추출
    approval_request_id = verify_result.get("approval_request_id", "")

    # evidence policy 생성
    evidence_policy = build_evidence_policy(profile)

    # Handoff payload 생성 (safe fields만)
    page_url_safe = _url_safe(page_url)
    safe_payload = _remove_forbidden_fields(kwargs)

    handoff_payload = {
        "action_name": ACTION_NAME,
        "business_profile": business_profile,
        "page_url_safe": page_url_safe,
        "submit_selector": submit_selector,
        "target_id": safe_payload.get("target_id", ""),
        "organization_name": safe_payload.get("organization_name", ""),
        "amount": safe_payload.get("amount", ""),
        "due_date": safe_payload.get("due_date", ""),
        "erp_module": safe_payload.get("erp_module", ""),
        "document_title": safe_payload.get("document_title", ""),
        "signer_name": safe_payload.get("signer_name", ""),
        "approver_name": safe_payload.get("approver_name", ""),
        "form_summary": safe_payload.get("form_summary", ""),
        "approval_request_id": approval_request_id,
        "approval_token": approval_token,
        "expected_result_markers": kwargs.get("expected_result_markers", []),
        "evidence_requirements": kwargs.get("evidence_requirements", {}),
        "evidence_policy": evidence_policy,
        "timeout_seconds": kwargs.get("timeout_seconds", 300),
        "headless": kwargs.get("headless", True),
        "created_at": datetime.now(UTC).isoformat(),
    }

    executed_at = datetime.now(UTC).isoformat()

    return {
        "ok": True,
        "verdict": "EXECUTE_HANDOFF_READY",
        "approval_status": "APPROVED_AND_CONSUMED",
        "approval_request_id": approval_request_id,
        "execution_location": "LOCAL_AGENT_REQUIRED",
        "handoff_required": True,
        "handoff_payload": handoff_payload,
        "evidence_policy": evidence_policy,
        "evidence": {
            "business_profile": business_profile,
            "verdict": "EXECUTE_HANDOFF_READY",
            "approval_request_id": approval_request_id,
            "execution_location": "LOCAL_AGENT_REQUIRED",
            "executed_at": executed_at,
        },
    }


register_handler(ACTION_NAME, execute)
