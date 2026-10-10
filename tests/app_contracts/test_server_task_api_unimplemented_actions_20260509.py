"""
미구현(implemented=False) 제출/투찰/전자서명 액션의 안전 차단 테스트 (2026-05-09).

검증:
- ActionSpec 등록은 유지
- 실제 실행 핸들러 등록 거부 (action_registry.register_handler)
- prepare_action_task verdict가 ACTION_REGISTERED_NOT_IMPLEMENTED
- 승인이 소비되어도 미구현 상태에서는 handoff 차단
"""
from __future__ import annotations

import pytest

from ai_orchestrator.agent_hub import action_registry
from ai_orchestrator.agent_hub.policy import user_approval_gate as gate
from ai_orchestrator.server import action_task_handoff as ath


_PENDING_ACTIONS = (
    "bid.prepare_bid",
    "bid.submit_with_user_approval",
    "esign.prepare_signature",
    "esign.execute_with_user_approval",
)


@pytest.fixture(autouse=True)
def _clear():
    gate.clear_all()
    yield
    gate.clear_all()


@pytest.mark.parametrize("name", _PENDING_ACTIONS)
def test_action_spec_registered(name):
    spec = action_registry.get_action_spec(name)
    assert spec is not None
    assert spec.implemented is False


@pytest.mark.parametrize("name", _PENDING_ACTIONS)
def test_register_handler_rejected_for_unimplemented(name):
    with pytest.raises(ValueError):
        action_registry.register_handler(name, lambda **_: {})


def test_bid_prepare_returns_not_implemented_no_approval():
    # bid.prepare_bid: AUTO_ALLOWED, requires_user_approval=False, implemented=False
    res = ath.prepare_action_task(
        action_name="bid.prepare_bid",
        params={"site": "g2b", "notice_no": "N-1"},
    )
    assert res["verdict"] == ath.VERDICT_NOT_IMPLEMENTED
    assert res["handoff_required"] is False
    assert res["handoff_payload"] is None
    assert res["blocked_reason"]


@pytest.mark.parametrize("name", (
    "bid.submit_with_user_approval",
    "esign.execute_with_user_approval",
))
def test_user_direct_actions_create_approval_but_block_execution(name):
    pending = ath.prepare_action_task(
        action_name=name,
        params={"site": "g2b", "notice_no": "N-1", "expected_result": "ok"},
    )
    # 승인 요청 자체는 만들어진다
    assert pending["verdict"] == ath.VERDICT_APPROVAL_REQUIRED
    assert pending["approval_request_id"]

    # 승인을 받아 토큰을 발급받아도 미구현이므로 handoff 차단
    token = gate.approve_request(pending["approval_request_id"], approver_user_id="u")["approval_token"]
    consumed = ath.prepare_action_task(
        action_name=name,
        params={"site": "g2b", "notice_no": "N-1", "expected_result": "ok"},
        approval_token=token,
    )
    assert consumed["verdict"] == ath.VERDICT_NOT_IMPLEMENTED
    assert consumed["approval_status"] == ath.APPROVAL_CONSUMED
    assert consumed["handoff_required"] is False
    assert consumed["handoff_payload"] is None
    assert consumed["blocked_reason"]


def test_implemented_actions_have_handlers_or_warning():
    # 구현된 액션 중 핸들러 등록이 안 된 경우 warning은 가능, but verdict는 정상
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://x"},
    )
    assert res["verdict"] == ath.VERDICT_HANDOFF_READY
