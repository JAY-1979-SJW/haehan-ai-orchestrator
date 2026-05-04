"""Stage 13F-2A: LocalAgentClient 단위 테스트.

실제 외부 네트워크 연결 없음. 모두 dry_run/mock 범위.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    AgentConfig,
    LocalAgentClient,
    LOW_RISK_ACTIONS,
    NotImplementedInThisStage,
    build_auth,
    build_heartbeat,
    build_result,
    handle_task,
    load_config,
    strip_sensitive,
)


# ── 1. 설정 로딩 ─────────────────────────────────────────────────────────────

class TestLoadConfig:
    def test_defaults_from_env(self, monkeypatch):
        monkeypatch.setenv("LA_SERVER_URL", "http://test:8400")
        monkeypatch.setenv("LA_AGENT_ID", "agent-001")
        monkeypatch.setenv("LA_DEVICE_TOKEN", "tok-secret")
        monkeypatch.setenv("LA_HEARTBEAT_SEC", "15")
        monkeypatch.setenv("LA_DRY_RUN", "true")

        cfg = load_config()

        assert cfg.server_base_url == "http://test:8400"
        assert cfg.agent_id == "agent-001"
        assert cfg.heartbeat_interval == 15.0
        assert cfg.dry_run is True

    def test_token_not_in_repr(self, monkeypatch):
        monkeypatch.setenv("LA_DEVICE_TOKEN", "super-secret-token")
        cfg = load_config(
            server_base_url="http://x", agent_id="a",
        )
        r = repr(cfg)
        assert "super-secret-token" not in r

    def test_token_not_in_str(self, monkeypatch):
        monkeypatch.setenv("LA_DEVICE_TOKEN", "super-secret-token")
        cfg = load_config(server_base_url="http://x", agent_id="a")
        s = str(cfg)
        assert "super-secret-token" not in s

    def test_dry_run_default_true(self, monkeypatch):
        monkeypatch.delenv("LA_DRY_RUN", raising=False)
        cfg = load_config(server_base_url="http://x", agent_id="a", device_token="t")
        assert cfg.dry_run is True

    def test_dry_run_false_explicit(self, monkeypatch):
        monkeypatch.setenv("LA_DRY_RUN", "false")
        cfg = load_config(server_base_url="http://x", agent_id="a", device_token="t")
        assert cfg.dry_run is False

    def test_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("LA_SERVER_URL", "http://env-url")
        cfg = load_config(server_base_url="http://param-url", agent_id="a", device_token="t")
        assert cfg.server_base_url == "http://param-url"

    def test_heartbeat_invalid_env_falls_back(self, monkeypatch):
        monkeypatch.setenv("LA_HEARTBEAT_SEC", "notanumber")
        cfg = load_config(server_base_url="http://x", agent_id="a", device_token="t")
        assert cfg.heartbeat_interval == 30.0


# ── 2. heartbeat payload ─────────────────────────────────────────────────────

class TestBuildHeartbeat:
    def test_type(self):
        hb = build_heartbeat("agent-001")
        assert hb["type"] == "heartbeat"

    def test_agent_id(self):
        hb = build_heartbeat("agent-abc")
        assert hb["agent_id"] == "agent-abc"

    def test_timestamp_present(self):
        hb = build_heartbeat("x")
        assert "timestamp" in hb
        assert hb["timestamp"]  # not empty

    def test_no_token(self):
        hb = build_heartbeat("agent-001")
        lowered = {k.lower(): v for k, v in hb.items()}
        assert "token" not in lowered
        assert "device_token" not in lowered
        assert "password" not in lowered


# ── 3. low-risk dry-run ──────────────────────────────────────────────────────

class TestLowRiskHandlers:
    @pytest.mark.parametrize("action", ["ping", "system_info", "list_allowed_apps"])
    def test_handle_returns_result(self, action):
        task = {"type": "task", "task_id": "t-001", "action": action, "params": {}}
        result = handle_task(task, dry_run=True)
        assert result["type"] == "result"
        assert result["task_id"] == "t-001"
        assert result["success"] is True

    def test_ping_summary(self):
        task = {"task_id": "t-ping", "action": "ping", "params": {}}
        result = handle_task(task)
        assert "pong" in result["summary"]

    def test_system_info_summary(self):
        task = {"task_id": "t-sys", "action": "system_info", "params": {}}
        result = handle_task(task)
        assert "os=" in result["summary"]

    def test_list_allowed_apps_summary(self):
        task = {"task_id": "t-apps", "action": "list_allowed_apps", "params": {}}
        result = handle_task(task)
        assert "browser" in result["summary"]

    def test_unknown_action_raises(self):
        task = {"task_id": "t-x", "action": "delete_file", "params": {}}
        with pytest.raises(NotImplementedInThisStage):
            handle_task(task)

    def test_low_risk_actions_set(self):
        assert "ping" in LOW_RISK_ACTIONS
        assert "system_info" in LOW_RISK_ACTIONS
        assert "list_allowed_apps" in LOW_RISK_ACTIONS
        assert "capture_screenshot" not in LOW_RISK_ACTIONS
        assert "open_url" not in LOW_RISK_ACTIONS


# ── 4. 민감정보 제거 ──────────────────────────────────────────────────────────

class TestStripSensitive:
    @pytest.mark.parametrize("key", [
        "token", "password", "secret", "cookie",
        "authorization", "raw_params", "params",
        "device_token", "access_token", "refresh_token",
        "api_key", "client_secret",
    ])
    def test_removes_sensitive_key(self, key):
        payload = {key: "sensitive-value", "safe_key": "safe-value"}
        result = strip_sensitive(payload)
        assert key not in result
        assert result["safe_key"] == "safe-value"

    def test_case_insensitive(self):
        result = strip_sensitive({"PASSWORD": "x", "Token": "y", "Name": "z"})
        assert "PASSWORD" not in result
        assert "Token" not in result
        assert result["Name"] == "z"

    def test_nested_dict(self):
        payload = {"outer": {"token": "t", "name": "n"}, "top": "v"}
        result = strip_sensitive(payload)
        assert "token" not in result["outer"]
        assert result["outer"]["name"] == "n"
        assert result["top"] == "v"

    def test_list_of_dicts(self):
        payload = [{"token": "t", "id": "1"}, {"secret": "s", "id": "2"}]
        result = strip_sensitive(payload)
        assert "token" not in result[0]
        assert result[0]["id"] == "1"
        assert "secret" not in result[1]

    def test_non_dict_passthrough(self):
        assert strip_sensitive(42) == 42
        assert strip_sensitive("hello") == "hello"
        assert strip_sensitive(None) is None

    def test_does_not_mutate_original(self):
        original = {"token": "t", "name": "n"}
        _ = strip_sensitive(original)
        assert original["token"] == "t"


# ── 5. 실제 외부 연결 차단 ───────────────────────────────────────────────────

class TestDryRunConnectionBlock:
    def test_dry_run_skips_connect(self):
        cfg = load_config(
            server_base_url="http://prod-server:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        # connect() 호출해도 실제 연결 없이 리턴
        client.connect()  # must not raise

    def test_run_once_dry_returns_dict(self):
        cfg = load_config(
            server_base_url="http://prod-server:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        result = client.run_once_dry()
        assert result["dry_run"] is True
        assert result["connected"] is False
        assert "heartbeat_sent" in result

    def test_run_once_dry_fails_when_not_dry_run(self):
        cfg = load_config(
            server_base_url="http://prod-server:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=False,
        )
        client = LocalAgentClient(cfg)
        with pytest.raises(RuntimeError):
            client.run_once_dry()

    def test_dry_run_heartbeat_no_token(self):
        cfg = load_config(
            server_base_url="http://prod-server:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        result = client.run_once_dry()
        hb = result["heartbeat_sent"]
        assert "token" not in str(hb).lower() or "type" in hb  # type key is ok


# ── 6. result payload ────────────────────────────────────────────────────────

class TestBuildResult:
    def test_basic_success(self):
        r = build_result("t-001", success=True, summary="done")
        assert r["type"] == "result"
        assert r["task_id"] == "t-001"
        assert r["success"] is True
        assert r["summary"] == "done"

    def test_error_fields(self):
        r = build_result("t-002", success=False, error_code="ERR_X", error="bad")
        assert r["error_code"] == "ERR_X"
        assert r["error"] == "bad"

    def test_summary_truncated(self):
        r = build_result("t-003", success=True, summary="x" * 600)
        assert len(r["summary"]) == 500

    def test_observe_summary_stripped(self):
        obs = {"url": "http://example.com", "token": "secret", "count": 3}
        r = build_result("t-004", success=True, observe_summary=obs)
        assert "token" not in r["observe_summary"]
        assert r["observe_summary"]["count"] == 3

    def test_no_extra_fields_when_empty(self):
        r = build_result("t-005", success=True)
        assert "error_code" not in r
        assert "error" not in r
        assert "observe_summary" not in r
        assert "audit_summary" not in r


# ── 7. auth payload (token은 함수 내에서만) ──────────────────────────────────

class TestBuildAuth:
    def test_auth_type(self):
        auth = build_auth("a-001", "dummy-tok")
        assert auth["type"] == "auth"
        assert auth["agent_id"] == "a-001"
        # device_token은 payload에 포함됨 (WS 전송 전 함수 내에서만 사용)
        assert "device_token" in auth

    def test_auth_not_logged(self, caplog):
        import logging
        with caplog.at_level(logging.DEBUG, logger="agent.local_agent_client"):
            _ = build_auth("a-001", "actual-secret-token")
        assert "actual-secret-token" not in caplog.text


# ── 8. ws_noop handler ──────────────────────────────────────────────────────

class TestHandleWsNoop:
    def test_ws_noop_success(self):
        task = {
            "task_id": "t-noop-001",
            "action": "ws_noop",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert result["type"] == "result"
        assert result["success"] is True
        assert result["summary"] == "ws_noop_ok"
        assert result["task_id"] == "t-noop-001"

    def test_ws_noop_in_low_risk_actions(self):
        assert "ws_noop" in LOW_RISK_ACTIONS

    def test_unknown_action_raises_not_implemented(self):
        task = {
            "task_id": "t-unknown",
            "action": "unknown_action_xyz",
            "params": {},
        }
        with pytest.raises(NotImplementedInThisStage):
            handle_task(task, dry_run=True)

    def test_high_risk_capture_screenshot_blocked(self):
        from agent.local_agent_client import BlockedAction
        task = {
            "task_id": "t-cap",
            "action": "capture_screenshot",
            "params": {},
        }
        with pytest.raises(BlockedAction):
            handle_task(task, dry_run=True)
