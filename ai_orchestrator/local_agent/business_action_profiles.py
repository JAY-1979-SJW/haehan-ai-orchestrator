"""범용 업무 프로필 정책 정의 — prepare/execute 핸들러 공용 참조."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

COMMON_FORBIDDEN_FIELDS = (
    "password", "otp", "cert_password", "private_key",
    "cookie", "session", "storage_state",
    "localStorage", "sessionStorage",
    "access_token", "refresh_token",
    "npki_data", "certificate_file_path",
)


@dataclass(frozen=True)
class BusinessProfile:
    """업무 프로필 정책 정의."""
    name: str
    label: str
    risk_level: str  # HIGH, MEDIUM, LOW
    requires_approval: bool
    required_summary_fields: tuple[str, ...]
    optional_summary_fields: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    approval_scope_fields: tuple[str, ...]
    required_evidence_fields: tuple[str, ...]
    allowed_result_fields: tuple[str, ...]
    default_expiry_seconds: int
    allowed_execution_location: str


_PROFILES: dict[str, BusinessProfile] = {
    "bid_submission": BusinessProfile(
        name="bid_submission",
        label="투찰 제출",
        risk_level="HIGH",
        requires_approval=True,
        required_summary_fields=("notice_id", "notice_title", "organization_name", "bid_amount", "due_date", "target_site"),
        optional_summary_fields=("attached_files", "submit_button_text"),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "notice_id", "bid_amount", "organization_name", "due_date"),
        required_evidence_fields=("business_profile", "verdict", "approval_request_id", "execution_location", "executed_at"),
        allowed_result_fields=("verdict", "notice_id", "organization_name", "bid_amount"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
    "erp_save": BusinessProfile(
        name="erp_save",
        label="ERP 저장",
        risk_level="MEDIUM",
        requires_approval=False,
        required_summary_fields=("erp_name", "menu_path", "record_type", "record_title", "changed_fields"),
        optional_summary_fields=("save_button_text",),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "erp_name", "record_type", "record_title"),
        required_evidence_fields=("business_profile", "verdict", "executed_at"),
        allowed_result_fields=("verdict", "erp_name", "record_type", "record_title"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
    "erp_submit_approval": BusinessProfile(
        name="erp_submit_approval",
        label="ERP 상신",
        risk_level="HIGH",
        requires_approval=True,
        required_summary_fields=("erp_name", "menu_path", "approval_title", "attached_files", "submit_button_text"),
        optional_summary_fields=("approval_amount", "approver_or_route"),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "erp_name", "approval_title", "approval_amount"),
        required_evidence_fields=("business_profile", "verdict", "approval_request_id", "execution_location", "executed_at"),
        allowed_result_fields=("verdict", "erp_name", "approval_title"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
    "document_submission": BusinessProfile(
        name="document_submission",
        label="문서 제출",
        risk_level="MEDIUM",
        requires_approval=False,
        required_summary_fields=("target_site", "document_title", "recipient_or_organization", "submit_button_text"),
        optional_summary_fields=("attached_files",),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "document_title", "recipient_or_organization"),
        required_evidence_fields=("business_profile", "verdict", "executed_at"),
        allowed_result_fields=("verdict", "document_title", "recipient_or_organization"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
    "public_agency_upload": BusinessProfile(
        name="public_agency_upload",
        label="공공기관 업로드",
        risk_level="MEDIUM",
        requires_approval=False,
        required_summary_fields=("agency_name", "service_name", "application_title", "attached_files"),
        optional_summary_fields=("deadline", "submit_button_text"),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "agency_name", "application_title"),
        required_evidence_fields=("business_profile", "verdict", "executed_at"),
        allowed_result_fields=("verdict", "agency_name", "application_title"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
    "esign_request": BusinessProfile(
        name="esign_request",
        label="전자서명 요청",
        risk_level="HIGH",
        requires_approval=True,
        required_summary_fields=("document_title", "signer_name", "organization_name", "signature_method", "target_site"),
        optional_summary_fields=("submit_button_text",),
        forbidden_fields=COMMON_FORBIDDEN_FIELDS,
        approval_scope_fields=("business_profile", "document_title", "signer_name"),
        required_evidence_fields=("business_profile", "verdict", "approval_request_id", "execution_location", "executed_at"),
        allowed_result_fields=("verdict", "document_title", "signer_name"),
        default_expiry_seconds=300,
        allowed_execution_location="LOCAL_AGENT_REQUIRED",
    ),
}


def get_profile(name: str) -> BusinessProfile | None:
    """프로필 조회."""
    return _PROFILES.get(name)


def list_profiles() -> list[str]:
    """모든 프로필 목록."""
    return list(_PROFILES.keys())


def validate_summary_fields(profile: BusinessProfile, params: dict[str, Any]) -> tuple[bool, list[str]]:
    """필수 요약 필드 검증. (ok, missing_fields)"""
    missing = [f for f in profile.required_summary_fields if not params.get(f)]
    return len(missing) == 0, missing


def build_approval_scope(profile: BusinessProfile, params: dict[str, Any]) -> dict[str, Any]:
    """승인 scope 생성 (params_hash에 포함될 필드 세트)."""
    scope = {}
    for field in profile.approval_scope_fields:
        scope[field] = params.get(field, "")
    return scope


def build_evidence_policy(profile: BusinessProfile) -> dict[str, Any]:
    """evidence policy 생성."""
    return {
        "profile_name": profile.name,
        "required_fields": profile.required_evidence_fields,
        "allowed_result_fields": profile.allowed_result_fields,
        "forbidden_fields": profile.forbidden_fields,
        "execution_location": profile.allowed_execution_location,
    }
