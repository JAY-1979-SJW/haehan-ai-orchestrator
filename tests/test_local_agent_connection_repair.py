"""LOCAL-DESKTOP-AGENT-CONNECTION-REPAIR-01 — register/auth/heartbeat/audit 테스트."""
from __future__ import annotations

import json

import pytest

from ai_orchestrator.agent_hub.registry import facade as reg
from ai_orchestrator.auth import registration_codes as rc
from core.agent_runtime.connection import connection_diagnostics as cd
from tools.audits.agent import audit_local_desktop_agent_connection as audit


@pytest.fixture(autouse=True)
def _clear_state():
    reg.clear()
    rc.clear()
    yield
    reg.clear()
    rc.clear()


# ── 1) registration code 발급 ────────────────────────────────────


def test_registration_code_issue_and_consume_once():
    res = rc.issue_code(label="test-agent",
                        expires_in_minutes=10,
                        issued_by="admin", issuer_role="admin")
    assert res.code.code_id
    raw = res.registration_code
    code = res.code
    # consume 성공
    rec = rc.consume_code(raw)
    assert rec.code_id == code.code_id
    # 재사용 불가
    with pytest.raises(Exception):
        rc.consume_code(raw)


# ── 2) register-with-code agent 등록 + device_token 1회 노출 ────


def test_register_agent_returns_device_token_once():
    res = reg.register_agent(host="hostA", os_name="Windows 11",
                             version="0.1.0", requested_by="admin")
    assert res.agent.agent_id.startswith("la-")
    # device_token 있고 hash 만 저장
    assert res.device_token
    assert res.agent.token_hash != res.device_token
    assert len(res.agent.token_hash) == 64  # sha256 hex


def test_register_agent_token_not_in_repr_or_stored():
    res = reg.register_agent(host="hostA", os_name="Linux",
                             version="0.1.0", requested_by="admin")
    fresh = reg.get_agent(res.agent.agent_id)
    # 저장된 LocalAgent 에 device_token 원문 필드 없음
    fields = fresh.__dataclass_fields__ if hasattr(fresh, '__dataclass_fields__') else {}
    assert "device_token" not in fields


# ── 3) authenticate_agent ──────────────────────────────────────


def test_authenticate_agent_with_correct_token():
    res = reg.register_agent(host="h", os_name="o", version="0.1.0",
                             requested_by="admin")
    ok = reg.authenticate_agent(res.agent.agent_id, res.device_token)
    assert ok is not None
    assert ok.agent_id == res.agent.agent_id


def test_authenticate_agent_with_bad_token_returns_none():
    res = reg.register_agent(host="h", os_name="o", version="0.1.0",
                             requested_by="admin")
    bad = reg.authenticate_agent(res.agent.agent_id, "garbage_token")
    assert bad is None


def test_authenticate_agent_unknown_id():
    bad = reg.authenticate_agent("la-doesnotexist", "x")
    assert bad is None


# ── 4) heartbeat / 상태 전환 ────────────────────────────────────


def test_agent_status_transitions_online_idle_stale_offline():
    res = reg.register_agent(host="h", os_name="o", version="0.1.0",
                             requested_by="admin")
    aid = res.agent.agent_id
    # 연결 직후 → online (구현체 따라 idle 가능)
    reg.set_agent_connected(aid)
    st = reg.get_agent_status(aid)
    assert st in ("online", "idle", "connected", "busy")
    # heartbeat
    reg.set_agent_last_seen(aid)
    st2 = reg.get_agent_status(aid)
    assert st2 in ("online", "idle", "connected", "busy")
    # disconnect
    reg.set_agent_disconnected(aid)
    st3 = reg.get_agent_status(aid)
    assert st3 in ("offline", "disconnected", "stale")


# ── 5) connection_diagnostics: URL 정규화 ──────────────────────


def test_normalize_ws_url_https_to_wss():
    u = cd.normalize_ws_url("https://api.haehan.ai")
    assert u == "wss://api.haehan.ai/api/v1/local-agents/ws"


def test_normalize_ws_url_http_to_ws():
    u = cd.normalize_ws_url("http://localhost:8080")
    assert u == "ws://localhost:8080/api/v1/local-agents/ws"


def test_normalize_ws_url_already_ws():
    u = cd.normalize_ws_url("wss://api.example.com")
    assert u == "wss://api.example.com/api/v1/local-agents/ws"


def test_normalize_ws_url_rejects_bad_scheme():
    with pytest.raises(ValueError):
        cd.normalize_ws_url("ftp://nope")


def test_normalize_ws_url_rejects_empty():
    with pytest.raises(ValueError):
        cd.normalize_ws_url("")


# ── 6) agent_id 마스킹 ────────────────────────────────────────


def test_mask_agent_id_format():
    assert cd.mask_agent_id("la-abc123def456") == "la-abc***f456"


def test_mask_agent_id_short_string():
    assert cd.mask_agent_id("la-abc") == "la***"


def test_mask_agent_id_empty():
    assert cd.mask_agent_id("") == ""


# ── 7) error code → 사용자 안내 ──────────────────────────────


def test_explain_error_known_codes():
    for code in ("AUTH_FAILED_4401", "REG_CODE_EXPIRED",
                 "REG_CODE_INVALID", "REG_CODE_ALREADY_USED",
                 "AUTH_TIMEOUT", "SERVER_NOT_REACHABLE",
                 "NETWORK_BLOCKED_PROXY", "HEARTBEAT_LOST",
                 "TOKEN_NOT_STORED"):
        msg = cd.explain_error(code)
        assert msg and len(msg) > 5


def test_explain_error_unknown_fallback():
    msg = cd.explain_error("__nope__")
    assert "로그를 확인" in msg or "Unknown" in msg or "알 수 없는" in msg


# ── 8) build_diagnostics ─────────────────────────────────────


def test_build_diagnostics_includes_masked_only():
    d = cd.build_diagnostics(
        server_base_url="https://api.example.com/x?token=SECRET&foo=1",
        agent_id="la-abc123def456",
        state=cd.STATE_AUTH_FAILED,
        last_heartbeat_iso="2026-05-21T01:00:00+09:00",
        last_error_code="AUTH_FAILED_4401",
        reconnect_count=3,
    )
    s = json.dumps(d.to_dict(), ensure_ascii=False)
    # token 원문 미노출
    assert "SECRET" not in s
    assert "[REDACTED]" in s
    # agent_id 원문 미노출
    assert "abc123def456" not in s
    assert "la-abc***f456" in s


def test_build_diagnostics_suggests_action_for_auth_failed():
    d = cd.build_diagnostics(
        server_base_url="https://api.example.com",
        agent_id="la-x", state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
    )
    assert d.suggested_actions
    assert any("재등록" in s for s in d.suggested_actions)


def test_auth_failed_recovery_requires_user_confirmed_reregister():
    plan = cd.build_recovery_plan(
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
        token_present=True,
    )
    assert plan.code == "AUTH_FAILED_4401"
    assert plan.next_action == "RE_REGISTER_REQUIRED"
    assert plan.requires_user_confirmation is True
    assert plan.can_auto_retry is False
    assert plan.should_delete_token is False
    assert any("--reset" in command for command in plan.commands)
    blob = json.dumps(plan.to_dict(), ensure_ascii=False)
    assert "device_token" not in blob
    assert "Bearer " not in blob


def test_heartbeat_lost_recovery_allows_auto_retry_without_token_delete():
    plan = cd.build_recovery_plan(
        state=cd.STATE_DISCONNECTED,
        last_error_code="HEARTBEAT_LOST",
        token_present=True,
    )
    assert plan.next_action == "AUTO_RECONNECT"
    assert plan.can_auto_retry is True
    assert plan.should_delete_token is False


def test_render_recovery_block_has_no_secret_values_for_auth_failed():
    plan = cd.build_recovery_plan(
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
        token_present=True,
    )
    block = cd.render_recovery_block(plan)
    assert "AUTH_FAILED_4401" in block
    assert "Bearer " not in block
    assert "registration_code=" not in block


def test_build_diagnostics_invalid_url_safe():
    d = cd.build_diagnostics(
        server_base_url="bad-url-no-scheme",
        agent_id="la-x", state=cd.STATE_SERVER_UNREACHABLE,
    )
    assert d.ws_url_redacted == "[INVALID_URL]"


# ── 9) render — 토큰 누출 없음 ───────────────────────────────


def test_render_user_block_has_no_token_leak():
    d = cd.build_diagnostics(
        server_base_url="https://api.example.com",
        agent_id="la-abc123def456", state=cd.STATE_CONNECTED,
        last_heartbeat_iso="2026-05-21T01:00:00+09:00",
    )
    block = cd.render_user_block(d)
    line = cd.render_one_line(d)
    # 어느 표시에도 token/secret/device_token 키워드 노출 안 됨
    for text in (block, line):
        leaks = cd.find_token_leaks(text)
        # state 자체 텍스트에 "session" 등은 없어야 함
        assert leaks == [], f"leak detected: {leaks}"


# ── 10) end-to-end (in-process, no WS) ──────────────────────


def test_e2e_register_with_code_and_authenticate_flow():
    """관리자 issue → 사용자 consume → register_agent → authenticate."""
    res = rc.issue_code(label="e2e-test", expires_in_minutes=10,
                        issued_by="admin")
    raw = res.registration_code
    consumed = rc.consume_code(raw)
    assert consumed.code_id == res.code.code_id
    # 서버: agent register + token 발급
    res = reg.register_agent(
        host="userPC", os_name="Win11", version="1.0.0",
        requested_by=f"registration_code:{consumed.code_id}",
    )
    # 클라이언트: WS auth (in-process 호출로 검증)
    auth = reg.authenticate_agent(res.agent.agent_id, res.device_token)
    assert auth is not None


def test_e2e_bad_token_fails_auth():
    res = reg.register_agent(host="h", os_name="o", version="0.1.0",
                             requested_by="admin")
    assert reg.authenticate_agent(res.agent.agent_id, "wrong") is None


# ── 11) audit verdict ─────────────────────────────────────


def test_audit_pass_when_e2e_clean_and_proxy_doc_present(tmp_path,
                                                          monkeypatch):
    e2e = {"register_ok": True, "auth_ok": True,
           "heartbeat_ok": True, "bad_token_4401_ok": True,
           "reconnect_ok": True}
    v = audit.judge_connection(
        e2e_results=e2e, token_leak_detected=False,
        proxy_doc_present=True, desktop_client_detected=True,
    )
    assert v.code == "PASS_LOCAL_DESKTOP_AGENT_CONNECTION_REPAIR", v.reasons


def test_audit_fail_device_token_leak():
    v = audit.judge_connection(token_leak_detected=True)
    assert v.code == "FAIL_DEVICE_TOKEN_LEAK"


def test_audit_fail_ws_auth_broken_when_auth_false():
    e2e = {"register_ok": True, "auth_ok": False}
    v = audit.judge_connection(e2e_results=e2e,
                               proxy_doc_present=True)
    assert v.code == "FAIL_WS_AUTH_BROKEN"


def test_audit_fail_heartbeat_broken():
    e2e = {"register_ok": True, "auth_ok": True, "heartbeat_ok": False}
    v = audit.judge_connection(e2e_results=e2e,
                               proxy_doc_present=True)
    assert v.code == "FAIL_HEARTBEAT_BROKEN"


def test_audit_fail_reconnect_broken():
    e2e = {"register_ok": True, "auth_ok": True,
           "heartbeat_ok": True, "reconnect_ok": False}
    v = audit.judge_connection(e2e_results=e2e,
                               proxy_doc_present=True)
    assert v.code == "FAIL_RECONNECT_BROKEN"


def test_audit_warn_proxy_doc_missing():
    e2e = {"register_ok": True, "auth_ok": True,
           "heartbeat_ok": True, "reconnect_ok": True}
    v = audit.judge_connection(e2e_results=e2e,
                               proxy_doc_present=False)
    assert v.code == "WARN_PROXY_CONFIG_UNVERIFIED"


def test_audit_warn_desktop_client_not_found():
    e2e = {"register_ok": True, "auth_ok": True,
           "heartbeat_ok": True, "reconnect_ok": True}
    v = audit.judge_connection(e2e_results=e2e,
                               proxy_doc_present=True,
                               desktop_client_detected=False)
    assert v.code == "WARN_DESKTOP_CLIENT_NOT_FOUND"


def test_audit_warn_installer_flow_incomplete():
    # 일부 e2e missing
    v = audit.judge_connection(e2e_results={"register_ok": True},
                               proxy_doc_present=True)
    assert v.code == "WARN_INSTALLER_FLOW_INCOMPLETE"


# ── 12) 회귀 가드 ────────────────────────────────────────


def test_regression_local_agent_router_imports():
    from ai_orchestrator.agent_hub.router import root as r
    assert hasattr(r, "local_agent_router")


def test_regression_registration_codes_imports():
    from ai_orchestrator.auth import registration_codes as rc
    assert hasattr(rc, "issue_code")
    assert hasattr(rc, "consume_code")


def test_regression_websocket_client_imports():
    from core.agent_runtime.connection import websocket_client
    assert hasattr(websocket_client, "run_forever")
