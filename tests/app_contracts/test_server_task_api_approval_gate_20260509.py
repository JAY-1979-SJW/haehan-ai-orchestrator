"""
서버 task API ↔ user_approval_gate 통합 테스트 (2026-05-09).

검증:
- browser.attach_file: 승인 요청 생성, 승인 전 실행 차단,
  승인 후 params_hash 일치 시 handoff 생성, 불일치/만료/재사용/action 불일치 차단.
"""

from __future__ import annotations

import time

import pytest

from ai_orchestrator.agent_hub.policy import user_approval_gate as gate
from ai_orchestrator.server import action_task_handoff as ath

_ATTACH_PARAMS = {
    "url": "https://www.g2b.go.kr/form",
    "form_field_label": "첨부파일",
    "file_name": "doc.hwpx",
    "file_size": 1234,
    "file_signature": "sha256:abc",
    "expected_result": "form 첨부 표시",
}


@pytest.fixture(autouse=True)
def _clear_state():
    gate.clear_all()
    yield
    gate.clear_all()


def test_attach_file_creates_approval_request_when_no_token():
    res = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        requested_by="user-1",
        user_intent_summary="입찰 첨부",
    )
    assert res["verdict"] == ath.VERDICT_APPROVAL_REQUIRED
    assert res["approval_status"] == ath.APPROVAL_PENDING
    assert res["approval_request_id"]
    assert res["handoff_required"] is False
    assert res["handoff_payload"] is None


def test_attach_file_blocked_until_approval():
    # token 없이 호출하면 절대 handoff_payload가 만들어지지 않음
    res = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    assert res["handoff_payload"] is None


def test_attach_file_handoff_after_valid_approval():
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    rid = pending["approval_request_id"]
    ok = gate.approve_request(rid, approver_user_id="user-1")
    assert ok["ok"]
    token = ok["approval_token"]

    consumed = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token=token,
    )
    assert consumed["verdict"] == ath.VERDICT_HANDOFF_READY
    assert consumed["approval_status"] == ath.APPROVAL_CONSUMED
    assert consumed["handoff_required"] is True
    assert consumed["handoff_payload"]["approval_token_required"] is True


def test_params_hash_mismatch_rejected():
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    rid = pending["approval_request_id"]
    token = gate.approve_request(rid, approver_user_id="u")["approval_token"]

    # params 변경
    modified = dict(_ATTACH_PARAMS)
    modified["file_name"] = "OTHER.hwpx"
    res = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=modified,
        approval_token=token,
    )
    assert res["verdict"] == ath.VERDICT_APPROVAL_INVALID
    assert "params_hash" in res["blocked_reason"] or "범위" in res["blocked_reason"]


def test_action_name_mismatch_rejected():
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    rid = pending["approval_request_id"]
    token = gate.approve_request(rid, approver_user_id="u")["approval_token"]

    # 다른 action(승인 필요)으로 토큰 재사용 시도 → action_name 불일치 차단
    res = ath.prepare_action_task(
        action_name="bid.submit_with_user_approval",
        params={"site": "g2b", "notice_no": "N-1"},
        approval_token=token,
    )
    assert res["verdict"] == ath.VERDICT_APPROVAL_INVALID


def test_token_single_use():
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    token = gate.approve_request(pending["approval_request_id"], approver_user_id="u")["approval_token"]

    first = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token=token,
    )
    assert first["verdict"] == ath.VERDICT_HANDOFF_READY

    second = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token=token,
    )
    assert second["verdict"] == ath.VERDICT_APPROVAL_INVALID


def test_token_expiry(monkeypatch):
    # 1초 만료로 만들기 (gate.create_approval_request는 최소 1초 허용)
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        duration_seconds=1,
    )
    token = gate.approve_request(pending["approval_request_id"], approver_user_id="u")["approval_token"]
    time.sleep(1.5)
    res = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token=token,
    )
    assert res["verdict"] == ath.VERDICT_APPROVAL_INVALID


def test_invalid_token():
    res = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token="not-a-real-token",
    )
    assert res["verdict"] == ath.VERDICT_APPROVAL_INVALID


def test_attach_file_handoff_payload_no_secrets():
    pending = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
    )
    token = gate.approve_request(pending["approval_request_id"], approver_user_id="u")["approval_token"]
    consumed = ath.prepare_action_task(
        action_name="browser.attach_file",
        params=_ATTACH_PARAMS,
        approval_token=token,
    )
    payload = consumed["handoff_payload"]
    violations = ath.validate_handoff_payload(payload)
    assert violations == []
    # params_safe에 민감 키 없음
    for k in payload["params_safe"]:
        assert k.lower() not in ("password", "otp", "cookie", "session", "storage_state", "private_key")
