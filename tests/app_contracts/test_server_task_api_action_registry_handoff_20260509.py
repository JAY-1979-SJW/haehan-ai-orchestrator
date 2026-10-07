"""
서버 task API ↔ action_registry handoff 통합 테스트 (2026-05-09).

검증:
- 알려진/알 수 없는 action_name 처리
- ActionSpec risk_level / requires_approval / execution_location 노출
- browser.download_file: 승인 없이 LOCAL_AGENT_REQUIRED handoff 생성
- 서버 직접 실행 없음 (handoff_target=LOCAL_AGENT_REQUIRED만 반환)
- safe summary 생성, forbidden field 미포함
- 민감 키 입력 차단
"""
from __future__ import annotations

import pytest

from ai_orchestrator.server import action_task_handoff as ath
from ai_orchestrator.agent_hub.policy.user_approval_gate import clear_all


@pytest.fixture(autouse=True)
def _clear_state():
    clear_all()
    yield
    clear_all()


def test_known_action_lookup_succeeds():
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://www.g2b.go.kr/x.zip", "expected_filename": "x.zip"},
    )
    assert res["action_name"] == "browser.download_file"
    assert res["implemented"] is True
    assert res["risk_level"] == "AUTO_ALLOWED"
    assert res["requires_approval"] is False
    assert res["execution_location"] == "LOCAL_AGENT_REQUIRED"


def test_unknown_action_blocked():
    res = ath.prepare_action_task(action_name="not.registered", params={})
    assert res["verdict"] == ath.VERDICT_UNKNOWN_ACTION
    assert res["handoff_required"] is False
    assert res["handoff_payload"] is None
    assert res["blocked_reason"]


def test_download_file_auto_handoff_no_approval():
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://www.g2b.go.kr/notice/file/123.hwpx", "expected_filename": "123.hwpx"},
    )
    assert res["verdict"] == ath.VERDICT_HANDOFF_READY
    assert res["approval_status"] == ath.APPROVAL_NOT_REQUIRED
    assert res["handoff_required"] is True
    assert res["handoff_target"] == "LOCAL_AGENT_REQUIRED"

    payload = res["handoff_payload"]
    assert payload is not None
    assert payload["execution_location"] == "LOCAL_AGENT_REQUIRED"
    assert payload["approval_token_required"] is False
    assert payload["sensitive_data_included"] is False
    assert payload["cookie_included"] is False
    assert payload["session_included"] is False
    assert payload["password_included"] is False
    assert payload["storage_state_included"] is False

    # validate
    assert ath.validate_handoff_payload(payload) == []


def test_download_file_summary_safe_url_only():
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://www.g2b.go.kr/notice/file/123.hwpx?token=SECRET&id=1"},
    )
    summary = res["summary"]
    assert "source_url_safe" in summary
    # 민감 query는 build_action_summary가 host+path만 노출하므로 token 미노출
    assert "SECRET" not in summary["source_url_safe"]


def test_server_does_not_execute_directly():
    # handoff_target은 항상 LOCAL_AGENT_REQUIRED. SERVER_DIRECT 경로 없음.
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://www.g2b.go.kr/x"},
    )
    assert res["execution_location"] == "LOCAL_AGENT_REQUIRED"
    assert res["handoff_target"] == "LOCAL_AGENT_REQUIRED"
    # 서버 직접 실행을 의미하는 키 없음
    assert "execute_now" not in res
    assert "server_executed" not in res


def test_sensitive_param_keys_blocked():
    for key in ("password", "otp", "cert_password", "cookie", "session", "storage_state", "private_key"):
        res = ath.prepare_action_task(
            action_name="browser.download_file",
            params={"source_url": "https://x", key: "VAL"},
        )
        assert res["verdict"] == ath.VERDICT_BLOCKED_SENSITIVE, f"key={key} not blocked"
        assert res["handoff_required"] is False
        assert res["blocked_reason"]


def test_handoff_evidence_policy_enforces_forbidden_fields():
    res = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://x"},
    )
    ep = res["handoff_payload"]["evidence_policy"]
    forbidden = set(ep["forbidden_fields"])
    for must in ("cookie", "session", "password", "otp", "private_key", "storage_state"):
        assert must in forbidden


def test_params_hash_deterministic_and_not_leaking_secrets():
    a = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"source_url": "https://x", "extra": "v"},
    )
    b = ath.prepare_action_task(
        action_name="browser.download_file",
        params={"extra": "v", "source_url": "https://x"},
    )
    assert a["params_hash"] == b["params_hash"]
    assert len(a["params_hash"]) == 64  # sha256 hex
