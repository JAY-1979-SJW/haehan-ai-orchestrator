"""
browser.submit_with_user_approval 핸들러 테스트
"""
import pytest

from ai_orchestrator.agent_hub.actions.browser_submit_with_user_approval import execute
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    create_approval_request,
    approve_request,
    _REQUESTS,
    _TOKENS,
)

ACTION_NAME = "browser.submit_with_user_approval"


@pytest.fixture(autouse=True)
def _clean():
    _REQUESTS.clear()
    _TOKENS.clear()
    yield
    _REQUESTS.clear()
    _TOKENS.clear()


def test_no_approval_token_required():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token="",
    )
    assert result["ok"] is False
    assert "APPROVAL_REQUIRED" in result["verdict"]


def test_handoff_ready_with_valid_token():
    # 1단계: 승인 요청 생성
    req = create_approval_request(
        action_name=ACTION_NAME,
        params={
            "page_url": "https://www.g2b.go.kr/submit/form",
            "submit_selector": "button.submit",
            "target_id": "공고 12345",
            "organization_name": "기관명",
            "amount": "100,000",
            "due_date": "2026-05-31",
        },
        summary={"user_intent_summary": "제출 승인"},
    )
    req_id = req["request_id"]

    # 2단계: 승인 (토큰 발급)
    approval = approve_request(req_id, approver_user_id="admin")
    assert approval["ok"] is True
    token = approval["approval_token"]

    # 3단계: 승인 토큰으로 handoff 생성
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token=token,
        target_id="공고 12345",
        organization_name="기관명",
        amount="100,000",
        due_date="2026-05-31",
    )
    assert result["ok"] is True
    assert result["verdict"] == "SUBMIT_HANDOFF_READY"
    assert result["approval_status"] == "APPROVED_AND_CONSUMED"
    assert "handoff_payload" in result
    assert result["handoff_required"] is True


def test_invalid_token_rejected():
    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token="invalid_token",
    )
    assert result["ok"] is False
    assert "APPROVAL_REJECTED" in result["verdict"]


def test_handoff_payload_structure():
    # 승인 생성 → 토큰 발급
    req = create_approval_request(
        action_name=ACTION_NAME,
        params={
            "page_url": "https://www.g2b.go.kr/submit/form",
            "submit_selector": "button.submit",
            "target_id": "12345",
            "organization_name": "기관",
            "amount": "100",
            "due_date": "2026-05-31",
        },
        summary={"user_intent_summary": "test"},
    )
    approval = approve_request(req["request_id"], approver_user_id="admin")
    token = approval["approval_token"]

    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token=token,
        target_id="12345",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
    )

    # handoff payload 확인
    payload = result["handoff_payload"]
    assert "action_name" in payload
    assert "page_url_safe" in payload
    assert "submit_selector" in payload
    assert "approval_request_id" in payload
    assert "approval_token" in payload


def test_no_server_direct_execution():
    """서버에서 직접 submit을 실행하지 않았는지 확인"""
    req = create_approval_request(
        action_name=ACTION_NAME,
        params={
            "page_url": "https://www.g2b.go.kr/submit/form",
            "submit_selector": "button.submit",
            "target_id": "12345",
            "organization_name": "기관",
            "amount": "100",
            "due_date": "2026-05-31",
        },
        summary={"user_intent_summary": "test"},
    )
    approval = approve_request(req["request_id"], approver_user_id="admin")
    token = approval["approval_token"]

    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token=token,
        target_id="12345",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
    )

    # 결과는 handoff이지, 직접 실행 결과가 아님
    assert result["verdict"] == "SUBMIT_HANDOFF_READY"
    assert result["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_evidence_collected():
    req = create_approval_request(
        action_name=ACTION_NAME,
        params={
            "page_url": "https://www.g2b.go.kr/submit/form",
            "submit_selector": "button.submit",
            "target_id": "12345",
            "organization_name": "기관",
            "amount": "100",
            "due_date": "2026-05-31",
        },
        summary={"user_intent_summary": "test"},
    )
    approval = approve_request(req["request_id"], approver_user_id="admin")
    token = approval["approval_token"]

    result = execute(
        page_url="https://www.g2b.go.kr/submit/form",
        submit_selector="button.submit",
        approval_token=token,
        target_id="12345",
        organization_name="기관",
        amount="100",
        due_date="2026-05-31",
    )
    assert result["ok"] is True
    assert "evidence" in result
