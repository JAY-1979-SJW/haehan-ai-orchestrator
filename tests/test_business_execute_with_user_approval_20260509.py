"""
범용 업무 실행 승인 액션 테스트 (2026-05-09).

검증:
- approval_token 필수
- 토큰 검증 및 1회 소비
- handoff_payload 생성 (safe fields만)
- 토큰 재사용 차단
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


def test_token_required():
    """토큰 없음 → APPROVAL_REQUIRED."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        submit_selector="button.submit",
        business_profile="bid_submission",
    )
    assert res["ok"] is False
    assert res["verdict"] == "APPROVAL_REQUIRED"
    assert res["approval_status"] == "NOT_PROVIDED"


def test_invalid_token():
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


def test_valid_token_creates_handoff():
    """유효 토큰 → EXECUTE_HANDOFF_READY + handoff_payload."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "target_id": "공고 12345",
        "organization_name": "기관명",
        "amount": "1,000,000",
        "due_date": "2026-05-31",
    }

    # 1단계: 승인 요청 생성
    req = create_approval_request("business.execute_with_user_approval", params, {})
    req_id = req["request_id"]

    # 2단계: 승인 토큰 발급
    appr = approve_request(req_id, approver_user_id="test_user")
    token = appr["approval_token"]

    # 3단계: execute 호출
    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res["ok"] is True
    assert res["verdict"] == "EXECUTE_HANDOFF_READY"
    assert res["approval_status"] == "APPROVED_AND_CONSUMED"
    assert res["handoff_required"] is True
    assert res["handoff_payload"] is not None


def test_handoff_payload_structure():
    """handoff_payload에 필수 필드 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "target_id": "공고 12345",
        "organization_name": "기관명",
        "amount": "1,000,000",
        "due_date": "2026-05-31",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    payload = res["handoff_payload"]
    assert payload["action_name"] == "business.execute_with_user_approval"
    assert payload["business_profile"] == "bid_submission"
    assert payload["page_url_safe"] == "https://www.g2b.go.kr"
    assert payload["submit_selector"] == "button.submit"
    assert payload["target_id"] == "공고 12345"
    assert payload["approval_token"] == token
    assert payload["created_at"]


def test_handoff_payload_excludes_forbidden_fields():
    """handoff_payload에 민감 필드 미포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
        "target_id": "공고 12345",
        "organization_name": "기관명",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    payload = res["handoff_payload"]
    forbidden_keys = {"password", "otp", "cert_password", "cookie", "session", "private_key"}
    # approval_token은 의도적으로 포함되어야 함
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
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    # 첫 번째 사용 — 성공
    res1 = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res1["ok"] is True

    # 두 번째 사용 — 실패 (토큰 이미 소비됨)
    res2 = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )
    assert res2["ok"] is False
    assert res2["verdict"] == "APPROVAL_REJECTED"


def test_page_url_missing():
    """page_url 없음 → ERROR."""
    res = business_execute_with_user_approval.execute(
        submit_selector="button",
        business_profile="bid_submission",
        approval_token="any",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "page_url" in res["error"]


def test_submit_selector_missing():
    """submit_selector 없음 → ERROR."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        business_profile="bid_submission",
        approval_token="any",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "submit_selector" in res["error"]


def test_business_profile_missing():
    """business_profile 없음 → ERROR."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        submit_selector="button",
        approval_token="any",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "business_profile" in res["error"]


def test_unsupported_business_profile():
    """지원하지 않는 프로필 → ERROR."""
    res = business_execute_with_user_approval.execute(
        page_url="https://www.g2b.go.kr",
        submit_selector="button",
        business_profile="unsupported",
        approval_token="any",
    )
    assert res["ok"] is False
    assert res["verdict"] == "ERROR"
    assert "미지원" in res["error"]


def test_response_has_evidence():
    """응답에 evidence 필드 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    assert "evidence" in res
    assert "business_profile" in res["evidence"]
    assert "verdict" in res["evidence"]
    assert "approval_request_id" in res["evidence"]
    assert "execution_location" in res["evidence"]
    assert res["evidence"]["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_response_has_evidence_policy():
    """응답에 evidence_policy 필드 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
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
    assert "forbidden_fields" in res["evidence_policy"]
    assert "execution_location" in res["evidence_policy"]
    assert res["evidence_policy"]["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_handoff_payload_has_evidence_policy():
    """handoff_payload에 evidence_policy 필드 포함."""
    params = {
        "page_url": "https://www.g2b.go.kr",
        "submit_selector": "button.submit",
        "business_profile": "bid_submission",
    }

    req = create_approval_request("business.execute_with_user_approval", params, {})
    token = approve_request(req["request_id"], "test_user")["approval_token"]

    res = business_execute_with_user_approval.execute(
        **params,
        approval_token=token,
    )

    payload = res["handoff_payload"]
    assert "evidence_policy" in payload
    assert payload["evidence_policy"]["profile_name"] == "bid_submission"
    assert "required_fields" in payload["evidence_policy"]
    assert "execution_location" in payload["evidence_policy"]
    assert payload["evidence_policy"]["execution_location"] == "LOCAL_AGENT_REQUIRED"
