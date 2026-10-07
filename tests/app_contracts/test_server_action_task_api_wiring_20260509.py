"""
API wiring 테스트: action_task_api → prepare_action_task 연결 검증
"""
import pytest

from ai_orchestrator.server.action_task_api import api_prepare_action
from ai_orchestrator.server.action_task_handoff import (
    VERDICT_HANDOFF_READY,
    VERDICT_APPROVAL_REQUIRED,
    VERDICT_UNKNOWN_ACTION,
    VERDICT_NOT_IMPLEMENTED,
)
from ai_orchestrator.agent_hub.policy.user_approval_gate import (
    approve_request,
    _REQUESTS,
    _TOKENS,
)
from ai_orchestrator.server.action_approval_audit_store import clear_store as clear_audit
from ai_orchestrator.server.action_evidence_store import clear_store as clear_evidence


@pytest.fixture(autouse=True)
def _clean():
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()
    yield
    _REQUESTS.clear()
    _TOKENS.clear()
    clear_audit()
    clear_evidence()


# 1. action prepare API가 prepare_action_task를 호출한다
def test_api_calls_prepare_action_task():
    result = api_prepare_action(
        action_name="browser.download_file",
        params={"url": "https://example.com/f.pdf"},
    )
    assert "verdict" in result
    assert "action_name" in result
    assert result["action_name"] == "browser.download_file"


# 2. 알 수 없는 action 차단
def test_unknown_action_blocked():
    result = api_prepare_action(action_name="does_not_exist", params={})
    assert result["verdict"] == VERDICT_UNKNOWN_ACTION


# 3. browser.download_file 요청 시 HANDOFF_READY (AUTO_ALLOWED, impl=True)
def test_download_file_handoff_ready():
    result = api_prepare_action(
        action_name="browser.download_file",
        params={"url": "https://www.g2b.go.kr/file.pdf"},
    )
    assert result["verdict"] == VERDICT_HANDOFF_READY
    assert result["handoff_required"] is True
    assert result["handoff_payload"] is not None


# 4. browser.attach_file 요청 시 APPROVAL_REQUIRED (USER_DELEGATED, impl=True)
def test_attach_file_approval_required():
    result = api_prepare_action(
        action_name="browser.attach_file",
        params={"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
        requested_by="test_user",
    )
    assert result["verdict"] == VERDICT_APPROVAL_REQUIRED
    assert result["approval_request_id"] is not None


# 5. 승인 토큰 제공 후 browser.attach_file HANDOFF_READY
def test_attach_file_with_approval_token_handoff_ready():
    prep = api_prepare_action(
        action_name="browser.attach_file",
        params={"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
        requested_by="test_user",
    )
    assert prep["verdict"] == VERDICT_APPROVAL_REQUIRED
    req_id = prep["approval_request_id"]

    approval = approve_request(req_id, approver_user_id="test_user")
    assert approval["ok"] is True
    token = approval["approval_token"]

    result = api_prepare_action(
        action_name="browser.attach_file",
        params={"file_path": "/tmp/bid.hwp", "field_selector": "#attach"},
        requested_by="test_user",
        approval_token=token,
    )
    assert result["verdict"] == VERDICT_HANDOFF_READY
    assert result["handoff_required"] is True


# 6. requires_approval=False + implemented=False → NOT_IMPLEMENTED (토큰 불필요)
@pytest.mark.parametrize("action_name", [
    "bid.prepare_bid",
    "esign.prepare_signature",
])
def test_no_approval_unimplemented_actions_not_implemented(action_name):
    result = api_prepare_action(action_name=action_name, params={"dummy": "val"})
    assert result["verdict"] == VERDICT_NOT_IMPLEMENTED
    assert result["implemented"] is False


# 7. requires_approval=True + implemented=False → 토큰 없이는 APPROVAL_REQUIRED
@pytest.mark.parametrize("action_name", [
    "bid.submit_with_user_approval",
    "esign.execute_with_user_approval",
])
def test_approval_required_unimplemented_returns_approval_required(action_name):
    result = api_prepare_action(action_name=action_name, params={"dummy": "val"})
    assert result["verdict"] == VERDICT_APPROVAL_REQUIRED
    assert result["implemented"] is False


# 8. requires_approval=True + implemented=False + token → NOT_IMPLEMENTED (실행 차단)
@pytest.mark.parametrize("action_name", [
    "bid.submit_with_user_approval",
    "esign.execute_with_user_approval",
])
def test_approval_unimplemented_with_token_not_implemented(action_name):
    prep = api_prepare_action(action_name=action_name, params={"dummy": "val"})
    assert prep["verdict"] == VERDICT_APPROVAL_REQUIRED
    req_id = prep["approval_request_id"]

    approval = approve_request(req_id, approver_user_id="test_user")
    assert approval["ok"] is True
    token = approval["approval_token"]

    result = api_prepare_action(
        action_name=action_name,
        params={"dummy": "val"},
        approval_token=token,
    )
    assert result["verdict"] == VERDICT_NOT_IMPLEMENTED
    assert result["implemented"] is False
