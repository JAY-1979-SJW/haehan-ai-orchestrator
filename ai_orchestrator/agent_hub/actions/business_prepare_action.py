"""범용 업무 실행 사전 검증 핸들러 — 업무 프로필별 필드 검증 + 안전 요약 생성."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.agent_hub.action_registry import register_handler
from ai_orchestrator.agent_hub.business_action_profiles import (
    COMMON_FORBIDDEN_FIELDS,
    build_approval_scope,
    build_evidence_policy,
    get_profile,
    validate_summary_fields,
)

ACTION_NAME = "business.prepare_action"


def _find_sensitive_keys(params: dict[str, Any]) -> tuple[list[str], list[str]]:
    """민감한 키 또는 값 문자열을 감지. (key names, values with keyword)"""
    sensitive_keys = []
    sensitive_values = []

    for key, val in params.items():
        key_lower = key.lower()
        if any(keyword in key_lower for keyword in COMMON_FORBIDDEN_FIELDS):
            sensitive_keys.append(key)
        elif isinstance(val, str):
            val_lower = val.lower()
            if any(keyword in val_lower for keyword in COMMON_FORBIDDEN_FIELDS):
                sensitive_values.append(key)

    return sensitive_keys, sensitive_values


def _url_safe(url: str) -> str:
    """URL에서 query/fragment 제거 (scheme://host/path만 보존)."""
    if not url:
        return ""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _attached_files_safe(attached_files: list[str] | None) -> list[str]:
    """파일 경로 리스트에서 basename만 추출."""
    if not attached_files:
        return []
    return [Path(f).name for f in attached_files if f]


def execute(**kwargs) -> dict[str, Any]:
    """
    범용 업무 실행 사전 검증.

    입력:
    - page_url: 업무 수행 페이지 URL (필수)
    - business_profile: 업무 프로필 (필수, 6종 중 하나)
    - 프로필별 필수 필드들
    - form_summary: 폼 요약 (선택)
    - attached_files: 첨부 파일 경로 리스트 (선택)

    출력:
    - verdict: PREPARE_SUCCESS 또는 PREPARE_WARN
    - business_profile: 입력받은 프로필명
    - page_url_safe: URL host+path (query 제거)
    - 프로필 필드들 (안전한 형태)
    - attached_files_safe: basename만
    - evidence: 감사 증거
    - warnings: 누락 필드 등
    """
    # 필수 필드 검증
    page_url = kwargs.get("page_url", "").strip()
    if not page_url:
        return {"ok": False, "verdict": "ERROR", "error": "page_url 필수"}

    business_profile = kwargs.get("business_profile", "").strip()
    if not business_profile:
        return {"ok": False, "verdict": "ERROR", "error": "business_profile 필수"}

    profile = get_profile(business_profile)
    if not profile:
        available = ", ".join(
            [
                "bid_submission",
                "erp_save",
                "erp_submit_approval",
                "document_submission",
                "public_agency_upload",
                "esign_request",
            ]
        )
        return {
            "ok": False,
            "verdict": "ERROR",
            "error": f"미지원 business_profile: {business_profile}. 지원: {available}",
        }

    # 민감 필드 감지
    sensitive_keys, sensitive_values = _find_sensitive_keys(kwargs)
    if sensitive_keys or sensitive_values:
        warnings = []
        if sensitive_keys:
            warnings.append(f"민감한 키 감지: {sensitive_keys}")
        if sensitive_values:
            warnings.append(f"민감한 값 감지: {sensitive_values}")
        return {
            "ok": False,
            "verdict": "BLOCKED_SENSITIVE",
            "error": "민감 필드 포함됨",
            "warnings": warnings,
        }

    # 프로필별 필수 필드 검증
    is_complete, missing_fields = validate_summary_fields(profile, kwargs)

    verdict = "PREPARE_SUCCESS"
    warnings = []
    if not is_complete:
        verdict = "PREPARE_WARN"
        warnings.append(f"필수 필드 누락: {missing_fields}")

    # 안전한 형태로 변환
    page_url_safe = _url_safe(page_url)
    attached_files = kwargs.get("attached_files")
    attached_files_safe = _attached_files_safe(attached_files) if isinstance(attached_files, list) else []

    # approval scope 생성
    approval_scope = build_approval_scope(profile, kwargs)

    # evidence policy 생성
    evidence_policy = build_evidence_policy(profile)

    # 응답 구성
    prepared_at = datetime.now(UTC).isoformat()

    result = {
        "ok": True,
        "verdict": verdict,
        "business_profile": business_profile,
        "profile_label": profile.label,
        "page_url_safe": page_url_safe,
        "form_summary": kwargs.get("form_summary", ""),
        "target_id": kwargs.get("target_id", ""),
        "organization_name": kwargs.get("organization_name", ""),
        "amount": kwargs.get("amount", ""),
        "due_date": kwargs.get("due_date", ""),
        "erp_module": kwargs.get("erp_module", ""),
        "record_type": kwargs.get("record_type", ""),
        "record_title": kwargs.get("record_title", ""),
        "document_title": kwargs.get("document_title", ""),
        "approver_name": kwargs.get("approver_name", ""),
        "signer_name": kwargs.get("signer_name", ""),
        "attached_files_safe": attached_files_safe,
        "prepared_at": prepared_at,
        "approval_scope": approval_scope,
        "evidence_policy": evidence_policy,
        "evidence": {
            "business_profile": business_profile,
            "verdict": verdict,
            "prepared_at": prepared_at,
        },
    }

    if warnings:
        result["warnings"] = warnings

    return result


register_handler(ACTION_NAME, execute)
