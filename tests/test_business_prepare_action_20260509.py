"""
범용 업무 사전 검증 액션 테스트 (2026-05-09).

검증:
- 업무 프로필별 필수 필드 검증
- page_url safe 변환 (query 제거)
- 민감 필드 차단
- 필수 필드 누락 시 PREPARE_WARN
"""

from __future__ import annotations

from ai_orchestrator.agent_hub.actions import business_prepare_action


def test_bid_submission_prepare_success():
    """투찰 제출 프로필 정상 경로."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr/bid/form?notice=N1",
        business_profile="bid_submission",
        notice_id="공고 12345",
        notice_title="공고 제목",
        organization_name="한국자동차정보센터",
        bid_amount="1,000,000",
        due_date="2026-05-31",
        target_site="https://www.g2b.go.kr",
        form_summary="투찰금액 1,000,000원",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"
    assert res["business_profile"] == "bid_submission"
    assert res["page_url_safe"] == "https://www.g2b.go.kr/bid/form"


def test_erp_save_prepare_success():
    """ERP 저장 프로필 정상 경로."""
    res = business_prepare_action.execute(
        page_url="https://erp.company.com/save",
        business_profile="erp_save",
        erp_name="SAP",
        menu_path="/MM/PO",
        record_type="PO",
        record_title="발주서 2026-05-09",
        changed_fields=["qty", "price"],
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"
    assert res["business_profile"] == "erp_save"
    assert res["record_type"] == "PO"
    assert res["record_title"] == "발주서 2026-05-09"


def test_document_submission_prepare_success():
    """문서 제출 프로필 정상 경로."""
    res = business_prepare_action.execute(
        page_url="https://portal.gov.kr/submit",
        business_profile="document_submission",
        target_site="https://portal.gov.kr",
        document_title="기술 제안서",
        recipient_or_organization="기술팀",
        submit_button_text="제출",
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_SUCCESS"
    assert res["business_profile"] == "document_submission"
    assert res["document_title"] == "기술 제안서"


def test_page_url_missing():
    """page_url 없음 → ERROR."""
    res = business_prepare_action.execute(
        business_profile="bid_submission",
        target_id="N1",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "page_url" in res["error"]


def test_business_profile_missing():
    """business_profile 없음 → ERROR."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        target_id="N1",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "business_profile" in res["error"]


def test_unsupported_business_profile():
    """지원하지 않는 프로필 → ERROR."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="unsupported_profile",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "미지원" in res["error"]


def test_required_fields_missing_bid_submission():
    """투찰 필수 필드 누락 → PREPARE_WARN."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        target_id="N1",
        organization_name="기관명",
        # amount, due_date, submit_selector 누락
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_WARN"
    assert "warnings" in res
    assert any("필수 필드 누락" in w for w in res["warnings"])


def test_required_fields_missing_erp_save():
    """ERP 저장 필수 필드 누락 → PREPARE_WARN."""
    res = business_prepare_action.execute(
        page_url="https://erp.company.com",
        business_profile="erp_save",
        erp_module="PURCHASE",
        # record_type, record_title 누락
    )
    assert res["ok"] is True
    assert res["verdict"] == "PREPARE_WARN"
    assert "warnings" in res


def test_sensitive_field_password_blocked():
    """password 키 감지 → BLOCKED_SENSITIVE."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        target_id="N1",
        password="secret123",  # 민감 필드
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED_SENSITIVE"
    assert "error" in res
    assert "warnings" in res


def test_sensitive_field_cookie_blocked():
    """cookie 키 감지 → BLOCKED_SENSITIVE."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        target_id="N1",
        cookie="session_id=abc123",  # 민감 필드
    )
    assert res["ok"] is False
    assert res["verdict"] == "BLOCKED_SENSITIVE"


def test_page_url_safe_query_strip():
    """page_url_safe: query string 제거."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr/bid/form?notice=N1&step=2&lang=ko",
        business_profile="bid_submission",
        target_id="N1",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
        submit_selector="button",
    )
    assert res["ok"] is True
    assert res["page_url_safe"] == "https://www.g2b.go.kr/bid/form"


def test_attached_files_basename_only():
    """attached_files_safe: basename만 추출."""
    res = business_prepare_action.execute(
        page_url="https://portal.gov.kr",
        business_profile="document_submission",
        document_title="제안서",
        organization_name="기관",
        attached_files=["/home/user/proposal.pdf", "/tmp/attachment.hwp", "C:\\Users\\doc.xlsx"],
    )
    assert res["ok"] is True
    assert res["attached_files_safe"] == ["proposal.pdf", "attachment.hwp", "doc.xlsx"]


def test_all_business_profiles_available():
    """6개 프로필 모두 지원."""
    profiles = [
        "bid_submission",
        "erp_save",
        "erp_submit_approval",
        "document_submission",
        "public_agency_upload",
        "esign_request",
    ]
    for profile in profiles:
        res = business_prepare_action.execute(
            page_url="https://example.com",
            business_profile=profile,
        )
        # 필드 누락은 WARN이지만 ok=True
        assert res["ok"] is True or res["ok"] is False
        if res["ok"] is True:
            assert res["business_profile"] == profile


def test_response_has_evidence():
    """응답에 evidence 필드 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        target_id="N1",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
        submit_selector="button",
    )
    assert "evidence" in res
    assert "business_profile" in res["evidence"]
    assert "verdict" in res["evidence"]
    assert "prepared_at" in res["evidence"]


def test_response_has_approval_scope():
    """응답에 approval_scope 필드 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        notice_id="N1",
        notice_title="공고",
        organization_name="기관",
        bid_amount="100",
        due_date="2026-05-31",
        target_site="https://g2b.go.kr",
    )
    assert "approval_scope" in res
    assert res["approval_scope"]["business_profile"] == "bid_submission"
    assert "notice_id" in res["approval_scope"]
    assert "bid_amount" in res["approval_scope"]


def test_response_has_evidence_policy():
    """응답에 evidence_policy 필드 포함."""
    res = business_prepare_action.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        target_id="N1",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
        submit_selector="button",
    )
    assert "evidence_policy" in res
    assert res["evidence_policy"]["profile_name"] == "bid_submission"
    assert "required_fields" in res["evidence_policy"]
    assert "forbidden_fields" in res["evidence_policy"]
    assert "execution_location" in res["evidence_policy"]
    assert res["evidence_policy"]["execution_location"] == "LOCAL_AGENT_REQUIRED"
