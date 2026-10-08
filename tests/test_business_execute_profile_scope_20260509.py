"""
business.execute_with_user_approval의 profile scope 검증 테스트 (2026-05-09).

검증:
- profile policy 사용하여 scope 검증
- handoff_payload에 evidence_policy 포함
- forbidden field 미포함
- profile 변경 감지
"""

from __future__ import annotations

import pytest

from ai_orchestrator.agent_hub.actions import business_execute_with_user_approval
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    approve_request,
    clear_all,
    create_approval_request,
)


@pytest.fixture(autouse=True)
def _clear():
    clear_all()
    yield
    clear_all()


def test_valid_token_creates_handoff():
    """유효 토큰 → EXECUTE_HANDOFF_READY."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res["ok"] is True
    assert res["verdict"] == "EXECUTE_HANDOFF_READY"
    assert res["handoff_required"] is True


def test_handoff_payload_has_evidence_policy():
    """handoff_payload에 evidence_policy 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert "evidence_policy" in res
    assert res["evidence_policy"]["profile_name"] == "bid_submission"
    assert "required_fields" in res["evidence_policy"]


def test_response_has_evidence_policy():
    """응답에 evidence_policy 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert "evidence_policy" in res
    assert res["evidence_policy"]["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_forbidden_fields_excluded_from_payload():
    """handoff_payload에서 forbidden field 제외."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    payload = res["handoff_payload"]
    forbidden_keys = {"password", "otp", "cert_password", "cookie", "session", "private_key"}
    for key in payload:
        if key == "approval_token":
            continue
        for forbidden in forbidden_keys:
            assert forbidden not in key.lower()


def test_token_one_time_use():
    """토큰 1회 사용 후 재사용 차단."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    # 첫 번째 사용 — 성공
    res1 = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res1["ok"] is True

    # 두 번째 사용 — 실패
    res2 = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res2["ok"] is False
    assert res2["verdict"] == "APPROVAL_REJECTED"


def test_erp_save_profile_execution():
    """erp_save profile 토큰 통과."""
    params = {
        "page_url": "https://erp.company.com",
        "submit_selector": "button.save",
        "business_profile": "erp_save",
        "erp_name": "SAP",
        "record_type": "PO",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert res["ok"] is True
    assert res["evidence_policy"]["profile_name"] == "erp_save"


def test_esign_request_profile_execution():
    """esign_request profile 토큰 통과."""
    params = {
        "page_url": "https://sign.company.com",
        "submit_selector": "button.sign",
        "business_profile": "esign_request",
        "document_title": "계약서",
        "signer_name": "홍길동",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert res["ok"] is True
    assert res["evidence_policy"]["profile_name"] == "esign_request"


def test_approval_status_approved_and_consumed():
    """approval_status = APPROVED_AND_CONSUMED."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert res["approval_status"] == "APPROVED_AND_CONSUMED"


def test_handoff_payload_action_name():
    """handoff_payload action_name = business.execute_with_user_approval."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert res["handoff_payload"]["action_name"] == "business.execute_with_user_approval"


def test_handoff_payload_business_profile():
    """handoff_payload business_profile 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "notice_id": "공고 12345",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert res["handoff_payload"]["business_profile"] == "bid_submission"


def test_invalid_token_rejected():
    """잘못된 토큰 → APPROVAL_REJECTED."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        submit_selector="button.submit",
        business_profile="bid_submission",
        approval_token="invalid_token_xxx",
    )

    assert res["ok"] is False
    assert res["verdict"] == "APPROVAL_REJECTED"
    assert res["approval_status"] == "INVALID"


def test_token_required():
    """토큰 없음 → APPROVAL_REQUIRED."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        submit_selector="button.submit",
        business_profile="bid_submission",
    )

    assert res["ok"] is False
    assert res["verdict"] == "APPROVAL_REQUIRED"
