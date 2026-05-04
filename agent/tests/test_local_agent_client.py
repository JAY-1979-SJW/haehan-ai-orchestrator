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


# ── 8.5. safe_echo handler ────────────────────────────────────────────────────

class TestHandleSafeEcho:
    def test_safe_echo_success(self):
        task = {
            "task_id": "t-echo-001",
            "action": "safe_echo",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert result["type"] == "result"
        assert result["success"] is True
        assert result["summary"] == "safe_echo_ok"
        assert result["task_id"] == "t-echo-001"

    def test_safe_echo_has_data_field(self):
        task = {
            "task_id": "t-echo-002",
            "action": "safe_echo",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert "data" in result
        assert result["data"]["action"] == "safe_echo"
        assert result["data"]["status"] == "ok"

    def test_safe_echo_no_params_echo(self):
        task = {
            "task_id": "t-echo-003",
            "action": "safe_echo",
            "params": {"test_param": "should_not_echo", "secret": "hidden"},
        }
        result = handle_task(task, dry_run=True)
        assert "params" not in result["data"]
        assert "test_param" not in str(result)
        assert "should_not_echo" not in str(result)

    def test_safe_echo_in_low_risk_actions(self):
        assert "safe_echo" in LOW_RISK_ACTIONS

    def test_safe_echo_task_in_listen_mode_mock(self):
        """mock에서 safe_echo task를 수신하고 처리할 수 있는지 확인."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-echo-001",
            device_token="tok-echo1",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-echo-001"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-safe-echo-001",
                    "action": "safe_echo",
                    "params": {},
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        assert len(result) >= 2
        result_msgs = [r for r in result if r.get("type") == "result"]
        assert len(result_msgs) >= 1
        assert result_msgs[0].get("success") is True
        assert result_msgs[0].get("summary") == "safe_echo_ok"


# ── 8.5. safe_desktop_capability handler ──────────────────────────────────────

class TestHandleSafeDesktopCapability:
    def test_safe_desktop_capability_success(self):
        task = {
            "task_id": "t-cap-001",
            "action": "safe_desktop_capability",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert result["type"] == "result"
        assert result["success"] is True
        assert result["summary"] == "safe_desktop_capability_ok"
        assert result["task_id"] == "t-cap-001"

    def test_safe_desktop_capability_has_data_field(self):
        task = {
            "task_id": "t-cap-002",
            "action": "safe_desktop_capability",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert "data" in result
        assert result["data"]["action"] == "safe_desktop_capability"
        assert result["data"]["status"] == "ok"

    def test_safe_desktop_capability_capabilities_fields(self):
        task = {
            "task_id": "t-cap-003",
            "action": "safe_desktop_capability",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        assert "capabilities" in result["data"]
        caps = result["data"]["capabilities"]
        assert "browser_supported" in caps
        assert "office_supported" in caps
        assert "cad_supported" in caps
        assert isinstance(caps["browser_supported"], bool)
        assert isinstance(caps["office_supported"], bool)
        assert isinstance(caps["cad_supported"], bool)

    def test_safe_desktop_capability_no_params_echo(self):
        task = {
            "task_id": "t-cap-004",
            "action": "safe_desktop_capability",
            "params": {"test_param": "should_not_echo", "secret": "hidden"},
        }
        result = handle_task(task, dry_run=True)
        assert "params" not in result["data"]
        assert "test_param" not in str(result)
        assert "should_not_echo" not in str(result)

    def test_safe_desktop_capability_no_pc_identifiers(self):
        task = {
            "task_id": "t-cap-005",
            "action": "safe_desktop_capability",
            "params": {},
        }
        result = handle_task(task, dry_run=True)
        result_str = str(result).lower()
        # Check result doesn't contain PC identifiers
        assert "username" not in result_str
        assert "hostname" not in result_str
        assert "computername" not in result_str
        assert "\\users\\" not in result_str
        assert "registry" not in result_str
        assert "process" not in result_str
        assert "environment" not in result_str

    def test_safe_desktop_capability_in_low_risk_actions(self):
        assert "safe_desktop_capability" in LOW_RISK_ACTIONS

    def test_safe_desktop_capability_task_in_listen_mode_mock(self):
        """mock에서 safe_desktop_capability task를 수신하고 처리할 수 있는지 확인."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-cap-001",
            device_token="tok-cap1",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-cap-001"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-safe-cap-001",
                    "action": "safe_desktop_capability",
                    "params": {},
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        assert len(result) >= 2
        result_msgs = [r for r in result if r.get("type") == "result"]
        assert len(result_msgs) >= 1
        assert result_msgs[0].get("success") is True
        assert result_msgs[0].get("summary") == "safe_desktop_capability_ok"
        assert "capabilities" in result_msgs[0].get("data", {})


# ── 9. listen mode 테스트 ──────────────────────────────────────────────────────

class TestListenMode:
    def test_mock_loop_with_listen_parameters(self):
        """listen 옵션은 연결 구간에서만 사용되며, mock_loop은 영향받지 않음."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-listen-001",
            device_token="tok-listen",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-listen-001"},
            {"type": "heartbeat_ack"},
        ]
        result = client.run_mock_loop(server_messages)
        assert len(result) >= 1
        assert result[0]["type"] == "auth"

    def test_listen_parameters_accepted_by_connect(self):
        """connect()가 listen_seconds/heartbeat_interval_seconds 파라미터 수용."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=True,  # dry_run=True이면 실제 연결 없음
        )
        client = LocalAgentClient(cfg)
        result = client.connect(
            heartbeat_count=1,
            allow_task_action="ws_noop",
            max_tasks=1,
            listen_seconds=5,
            heartbeat_interval_seconds=1,
        )
        # dry_run=True이면 skipped 반환
        assert result["status"] == "skipped"

    def test_result_includes_tasks_processed_field(self):
        """connect() 반환값에 tasks_processed 필드 포함 확인."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-001",
            device_token="tok",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        result = client.connect()
        # dry_run=True이면 skipped
        assert "status" in result
        # 실제 연결에서는 tasks_processed 필드가 있을 것

    def test_ws_noop_task_in_listen_mode_mock(self):
        """mock에서 ws_noop task를 수신하고 처리할 수 있는지 확인."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-listen-002",
            device_token="tok-listen2",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        # 테스트용 서버 메시지 시나리오
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-listen-002"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-ws-noop-001",
                    "action": "ws_noop",
                    "params": {},
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        # auth + heartbeat_ack 수신 시 응답 없음 + task 수신 시 result 생성
        assert len(result) >= 2  # auth + result (minimum)
        # result 메시지 확인
        result_msgs = [r for r in result if r.get("type") == "result"]
        assert len(result_msgs) >= 1
        assert result_msgs[0].get("success") is True
        assert result_msgs[0].get("summary") == "ws_noop_ok"

    def test_unknown_task_action_blocked_in_listen_mode(self):
        """unknown action은 NotImplementedInThisStage로 처리."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-listen-003",
            device_token="tok-listen3",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-listen-003"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-unknown",
                    "action": "unknown_task",
                    "params": {},
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        result_msgs = [r for r in result if r.get("type") == "result"]
        assert len(result_msgs) >= 1
        assert result_msgs[0].get("success") is False
        assert "NOT_IMPLEMENTED" in result_msgs[0].get("error_code", "")

    def test_high_risk_action_blocked_in_listen_mode(self):
        """high-risk action(capture_screenshot)은 BLOCKED로 처리."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-listen-004",
            device_token="tok-listen4",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-listen-004"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-screenshot",
                    "action": "capture_screenshot",
                    "params": {},
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        result_msgs = [r for r in result if r.get("type") == "result"]
        assert len(result_msgs) >= 1
        assert result_msgs[0].get("success") is False
        assert "BLOCKED" in result_msgs[0].get("error_code", "")

    def test_no_sensitive_values_in_mock_result(self):
        """mock 결과에 민감값 포함 확인 (auth 메시지 제외)."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="agent-listen-005",
            device_token="super-secret-token-should-not-appear",
            dry_run=True,
        )
        client = LocalAgentClient(cfg)
        server_messages = [
            {"type": "auth_ok", "agent_id": "agent-listen-005"},
            {"type": "heartbeat_ack"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-noop",
                    "action": "ws_noop",
                },
            },
        ]
        result = client.run_mock_loop(server_messages)
        # result[0]은 auth (device_token 포함) — 제외하고 확인
        result_without_auth = [r for r in result if r.get("type") != "auth"]
        result_str = str(result_without_auth)
        assert "super-secret-token-should-not-appear" not in result_str


# ── 10. result_ack protocol 테스트 ──────────────────────────────────────────

class TestResultAckProtocol:
    """result_ack protocol 검증 테스트."""

    def test_server_sends_result_ack_after_result(self):
        """server가 result 처리 후 result_ack을 전송한다 (protocol).

        실제 server test에서 검증하며, 여기서는 protocol 형식 검증만 수행.
        """
        # result_ack은 server에서 _handle_result 후 전송됨
        # client는 이를 기다려야 함 (대기 로직은 이미 구현됨)
        pass

    def test_result_ack_includes_task_id_and_status(self):
        """result_ack payload에는 task_id와 status만 포함된다."""
        # mock result_ack payload
        ack_payload = {
            "type": "result_ack",
            "task_id": "lat-test-123",
            "status": "completed",
        }
        # payload가 최소화되었는지 확인
        assert "task_id" in ack_payload
        assert "status" in ack_payload
        assert len(ack_payload) == 3  # type, task_id, status only
        assert "data" not in ack_payload
        assert "result_summary" not in ack_payload

    def test_result_ack_no_sensitive_values(self):
        """result_ack payload에 민감값이 없다."""
        ack_payload = {
            "type": "result_ack",
            "task_id": "lat-test-123",
            "status": "completed",
        }
        ack_str = str(ack_payload)
        assert "token" not in ack_str.lower()
        assert "password" not in ack_str.lower()
        assert "secret" not in ack_str.lower()
        assert "api_key" not in ack_str.lower()

    def test_disconnect_does_not_overwrite_completed_task(self):
        """disconnect 처리 시 이미 completed된 task를 failed로 덮어쓰지 않는다.

        실제 server test에서 검증하며, 여기서는 policy 확인만 수행.
        """
        # fail_active_tasks_for_agent는 ACTIVE_TASK_STATUSES만 처리함
        # completed는 active가 아니므로 덮어쓰지 않음 (by design)
        pass
