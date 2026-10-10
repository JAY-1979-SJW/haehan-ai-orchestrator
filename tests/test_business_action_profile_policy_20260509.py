"""
범용 업무 프로필 정책 테스트 (2026-05-09).

검증:
- 6개 profile 모두 등록
- profile별 required_summary_fields 존재
- COMMON_FORBIDDEN 포함
- approval_scope_fields에 business_profile 포함
- build_approval_scope() / build_evidence_policy() 동작
"""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_hub.business_action_profiles import (
    COMMON_FORBIDDEN_FIELDS,
    build_approval_scope,
    build_evidence_policy,
    get_profile,
    list_profiles,
    validate_summary_fields,
)


def test_all_profiles_registered():
    """6개 profile 모두 등록."""
    profiles = list_profiles()
    expected = {
        "bid_submission",
        "erp_save",
        "erp_submit_approval",
        "document_submission",
        "public_agency_upload",
        "esign_request",
    }
    assert expected == set(profiles)


def test_get_profile_bid_submission():
    """bid_submission profile 조회."""
    p = get_profile("bid_submission")
    assert p is not None
    assert p.name == "bid_submission"
    assert p.label == "투찰 제출"
    assert p.risk_level == "HIGH"
    assert p.requires_approval is True


def test_get_profile_erp_save():
    """erp_save profile 조회."""
    p = get_profile("erp_save")
    assert p is not None
    assert p.label == "ERP 저장"
    assert p.risk_level == "MEDIUM"
    assert p.requires_approval is False


def test_get_profile_esign_request():
    """esign_request profile 조회."""
    p = get_profile("esign_request")
    assert p is not None
    assert p.label == "전자서명 요청"
    assert p.risk_level == "HIGH"
    assert p.requires_approval is True


def test_unknown_profile_returns_none():
    """미지원 profile → None."""
    p = get_profile("unknown_profile")
    assert p is None


def test_profile_required_summary_fields():
    """profile별 required_summary_fields 정의됨."""
    for name in list_profiles():
        p = get_profile(name)
        assert p.required_summary_fields
        assert isinstance(p.required_summary_fields, tuple)
        assert len(p.required_summary_fields) > 0


def test_profile_optional_summary_fields():
    """profile별 optional_summary_fields 정의됨."""
    for name in list_profiles():
        p = get_profile(name)
        assert isinstance(p.optional_summary_fields, tuple)


def test_common_forbidden_fields_included():
    """모든 profile에 COMMON_FORBIDDEN_FIELDS 포함."""
    for name in list_profiles():
        p = get_profile(name)
        for field in COMMON_FORBIDDEN_FIELDS:
            assert field in p.forbidden_fields, f"{name}에 {field} 미포함"


def test_approval_scope_fields_includes_profile():
    """모든 profile의 approval_scope_fields에 business_profile 포함."""
    for name in list_profiles():
        p = get_profile(name)
        assert "business_profile" in p.approval_scope_fields


def test_approval_scope_fields_include_critical_data():
    """프로필별 approval_scope_fields에 주요 데이터 포함."""
    # bid_submission: notice_id, bid_amount
    p = get_profile("bid_submission")
    assert "notice_id" in p.approval_scope_fields
    assert "bid_amount" in p.approval_scope_fields

    # esign_request: document_title, signer_name
    p = get_profile("esign_request")
    assert "document_title" in p.approval_scope_fields
    assert "signer_name" in p.approval_scope_fields


def test_validate_summary_fields_success():
    """필수 필드 충족 → (True, [])."""
    p = get_profile("bid_submission")
    params = {
        "notice_id": "공고 12345",
        "notice_title": "공고 제목",
        "organization_name": "기관명",
        "bid_amount": "1,000,000",
        "due_date": "2026-05-31",
        "target_site": "https://g2b.go.kr",
    }
    is_complete, missing = validate_summary_fields(p, params)
    assert is_complete is True
    assert missing == []


def test_validate_summary_fields_missing():
    """필수 필드 누락 → (False, [missing_list])."""
    p = get_profile("bid_submission")
    params = {
        "notice_id": "공고 12345",
        # 다른 필드 누락
    }
    is_complete, missing = validate_summary_fields(p, params)
    assert is_complete is False
    assert len(missing) > 0
    assert "notice_title" in missing


def test_build_approval_scope_structure():
    """build_approval_scope() 반환 구조."""
    p = get_profile("bid_submission")
    params = {
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
        "bid_amount": "1,000,000",
        "organization_name": "기관명",
        "due_date": "2026-05-31",
    }
    scope = build_approval_scope(p, params)
    assert isinstance(scope, dict)
    assert scope["business_profile"] == "bid_submission"
    assert scope["notice_id"] == "공고 12345"
    assert scope["bid_amount"] == "1,000,000"


def test_build_approval_scope_missing_fields():
    """필드 누락 시 build_approval_scope() 빈 문자열 포함."""
    p = get_profile("bid_submission")
    params = {"business_profile": "bid_submission"}  # 다른 필드 없음
    scope = build_approval_scope(p, params)
    assert scope["business_profile"] == "bid_submission"
    assert scope["notice_id"] == ""
    assert scope["bid_amount"] == ""


def test_build_evidence_policy_structure():
    """build_evidence_policy() 반환 구조."""
    p = get_profile("bid_submission")
    policy = build_evidence_policy(p)
    assert isinstance(policy, dict)
    assert policy["profile_name"] == "bid_submission"
    assert "required_fields" in policy
    assert "allowed_result_fields" in policy
    assert "forbidden_fields" in policy
    assert "execution_location" in policy


def test_evidence_policy_required_fields():
    """evidence_policy에 required_fields 포함."""
    for name in list_profiles():
        p = get_profile(name)
        policy = build_evidence_policy(p)
        assert policy["required_fields"] == p.required_evidence_fields
        assert len(policy["required_fields"]) > 0


def test_all_profiles_have_execution_location():
    """모든 profile은 allowed_execution_location = LOCAL_AGENT_REQUIRED."""
    for name in list_profiles():
        p = get_profile(name)
        assert p.allowed_execution_location == "LOCAL_AGENT_REQUIRED"


def test_dataclass_frozen():
    """BusinessProfile은 frozen."""
    p = get_profile("bid_submission")
    with pytest.raises(AttributeError):
        p.name = "changed"


def test_all_profiles_have_default_expiry():
    """모든 profile은 default_expiry_seconds 정의."""
    for name in list_profiles():
        p = get_profile(name)
        assert p.default_expiry_seconds > 0
        assert p.default_expiry_seconds == 300
