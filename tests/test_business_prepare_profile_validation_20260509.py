"""
business.prepare_action의 profile policy 연동 테스트 (2026-05-09).

검증:
- profile policy 사용하여 필수 필드 검증
- approval_scope, evidence_policy 반환
- forbidden field 차단
- profile별 필드 누락 시 PREPARE_WARN
"""

from __future__ import annotations

from ai_orchestrator.agent_hub.actions import business_prepare_action


def test_bid_submission_with_all_fields():
    """bid_submission 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고 제목",
        organization_name="기관명",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://www.g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"
    assert "approval_scope" in res
    assert "evidence_policy" in res
    assert res["approval_scope"]["business_profile"] == "bid_submission"


def test_bid_submission_missing_notice_title():
    """bid_submission notice_title 누락 → PREPARE_WARN."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        # notice_title 누락
        organization_name="기관명",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://www.g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_WARN"
    assert "warnings" in res
    assert any("필수 필드 누락" in w for w in res["warnings"])


def test_erp_save_with_all_fields():
    """erp_save 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://erp.company.com",
        business_profile="erp_save",
        erp_name="SAP",
        menu_path="/MM/PO",
        record_type="PO",
        record_title="발주서",
        changed_fields=["qty", "price"],
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"
    assert res["approval_scope"]["business_profile"] == "erp_save"


def test_erp_submit_approval_with_all_fields():
    """erp_submit_approval 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://erp.company.com",
        business_profile="erp_submit_approval",
        erp_name="SAP",
        menu_path="/FI/AP",
        approval_title="결재 상신",
        attached_files=["/tmp/file.pdf"],
        submit_button_text="상신",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"


def test_document_submission_with_all_fields():
    """document_submission 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://portal.gov.kr",
        business_profile="document_submission",
        target_site="https://portal.gov.kr",
        document_title="기술 제안서",
        recipient_or_organization="기술팀",
        submit_button_text="제출",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"


def test_public_agency_upload_with_all_fields():
    """public_agency_upload 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://agency.gov.kr",
        business_profile="public_agency_upload",
        agency_name="국토부",
        service_name="건축허가",
        application_title="건축신청",
        attached_files=["/tmp/plan.pdf"],
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"


def test_esign_request_with_all_fields():
    """esign_request 모든 필수 필드 입력."""
    res = business_prepare_action.execute(
        page_url="https://sign.company.com",
        business_profile="esign_request",
        document_title="계약서",
        signer_name="홍길동",
        organization_name="기업명",
        signature_method="공인인증서",
        target_site="https://sign.company.com",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"


def test_forbidden_field_password_blocked():
    """password 필드 → BLOCKED_SENSITIVE."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        password="secret123",  # 민감 필드
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED_SENSITIVE"


def test_forbidden_field_cookie_blocked():
    """cookie 필드 → BLOCKED_SENSITIVE."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        cookie="session_id=abc",  # 민감 필드
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED_SENSITIVE"


def test_forbidden_field_storage_state_blocked():
    """storage_state 필드 → BLOCKED_SENSITIVE."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        storage_state="{}",  # 민감 필드
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED_SENSITIVE"


def test_url_safe_query_strip():
    """page_url_safe: query string 제거."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr/form?notice=N1&lang=ko",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="100",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["page_url_safe"] == "https://www.g2b.go.kr/form"


def test_attached_files_basename_only():
    """attached_files_safe: basename만."""
    res = business_prepare_action.execute(
        page_url="https://portal.gov.kr",
        business_profile="public_agency_upload",
        agency_name="국토부",
        service_name="허가",
        application_title="신청",
        attached_files=["/home/user/proposal.pdf", "/tmp/document.hwp"],
    )
    assert res["ok"] is True
    assert res["attached_files_safe"] == ["proposal.pdf", "document.hwp"]


def test_approval_scope_includes_business_profile():
    """approval_scope에 business_profile 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["approval_scope"]["business_profile"] == "bid_submission"


def test_approval_scope_includes_bid_amount():
    """bid_submission approval_scope에 bid_amount 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="5,000,000",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["approval_scope"]["bid_amount"] == "5,000,000"


def test_evidence_policy_has_required_fields():
    """evidence_policy에 required_fields 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    assert "evidence_policy" in res
    assert "required_fields" in res["evidence_policy"]
    assert len(res["evidence_policy"]["required_fields"]) > 0


def test_evidence_policy_has_forbidden_fields():
    """evidence_policy에 forbidden_fields 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    policy = res["evidence_policy"]
    assert "forbidden_fields" in policy
    assert "password" in policy["forbidden_fields"]
    assert "cookie" in policy["forbidden_fields"]


def test_evidence_policy_execution_location():
    """evidence_policy execution_location = LOCAL_AGENT_REQUIRED."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고",
        organization_name="기관",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert res["ok"] is True
    assert res["evidence_policy"]["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_all_profiles_validation():
    """6개 프로필 모두 검증."""
    profiles = [
        (
            "bid_submission",
            {
                "notice_id": "1",
                "notice_title": "t",
                "organization_name": "o",
                "bid_amount": "1",
                "due_date": "d",
                "target_site": "s",
            },
        ),
        (
            "erp_save",
            {"erp_name": "e", "menu_path": "m", "record_type": "r", "record_title": "t", "changed_fields": ["f"]},
        ),
        (
            "erp_submit_approval",
            {
                "erp_name": "e",
                "menu_path": "m",
                "approval_title": "a",
                "attached_files": ["f"],
                "submit_button_text": "b",
            },
        ),
        (
            "document_submission",
            {"target_site": "s", "document_title": "d", "recipient_or_organization": "r", "submit_button_text": "b"},
        ),
        (
            "public_agency_upload",
            {"agency_name": "a", "service_name": "s", "application_title": "t", "attached_files": ["f"]},
        ),
        (
            "esign_request",
            {
                "document_title": "d",
                "signer_name": "s",
                "organization_name": "o",
                "signature_method": "m",
                "target_site": "s",
            },
        ),
    ]
    for profile_name, required_params in profiles:
        res = business_prepare_action.execute(
            page_url="https://example.com", business_profile=profile_name, **required_params
        )
        assert res["ok"] is True, f"{profile_name} failed"
        assert res["verdict"] == "PREPARE_SUCCESS"
        assert res["approval_scope"]["business_profile"] == profile_name
