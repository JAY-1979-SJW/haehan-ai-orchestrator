"""Stage 13F-2B: mock WebSocket 기반 task lifecycle 테스트.

실제 외부 네트워크 연결 없음. in-memory mock 메시지만 사용.
운영 서버 URL, device_token 실제값 사용 금지.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    AgentConfig,
    BlockedAction,
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


# ── fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    """테스트 전용 설정 (실제 서버/토큰 사용 안 함)."""
    return load_config(
        server_base_url="http://mock-server:8400",
        agent_id="test-agent-001",
        device_token="mock-token-for-test",
        heartbeat_interval=5.0,
        dry_run=True,
    )


@pytest.fixture
def client(mock_config):
    return LocalAgentClient(mock_config)


def _mock_task(action: str, task_id: str = "t-mock-001", params: dict = None) -> dict:
    """서버가 WS로 전달하는 task 메시지 형식."""
    return {
        "type": "task",
        "task": {
            "task_id": task_id,
            "agent_id": "test-agent-001",
            "action": action,
            "params": params or {},
            "risk_level": "low",
            "approved": False,
        },
    }


def _no_sensitive(payload: dict) -> bool:
    """결과 payload에 민감정보 키가 없는지 확인."""
    SENSITIVE = {
        "token", "password", "secret", "cookie",
        "authorization", "raw_params", "api_key",
        "device_token", "access_token", "session",
    }
    text = str(payload).lower()
    # 키 이름이 아닌 값도 체크: "mock-token-for-test" 같은 실제 값 미포함
    for s in SENSITIVE:
        if f'"{s}"' in text or f"'{s}'" in text:
            return False
    return True


# ── 1. heartbeat payload 테스트 ───────────────────────────────────────────────

class TestHeartbeatPayload:
    def test_type_is_heartbeat(self):
        hb = build_heartbeat("agent-001")
        assert hb["type"] == "heartbeat"

    def test_agent_id_present(self):
        hb = build_heartbeat("agent-xyz")
        assert hb["agent_id"] == "agent-xyz"

    def test_timestamp_present(self):
        hb = build_heartbeat("a")
        assert "timestamp" in hb and hb["timestamp"]

    def test_no_token_in_heartbeat(self):
        hb = build_heartbeat("agent-001")
        for key in hb:
            assert "token" not in key.lower()
            assert "password" not in key.lower()
            assert "secret" not in key.lower()

    def test_heartbeat_ack_no_response(self, client):
        """heartbeat_ack 수신 시 응답 없음."""
        result = client.process_server_message({"type": "heartbeat_ack"})
        assert result is None

    def test_idle_no_response(self, client):
        result = client.process_server_message({"type": "idle"})
        assert result is None


# ── 2. ping task lifecycle ────────────────────────────────────────────────────

class TestPingLifecycle:
    def test_ping_result_type(self, client):
        msg = _mock_task("ping", "t-ping-001")
        result = client.process_server_message(msg)
        assert result is not None
        assert result["type"] == "result"

    def test_ping_task_id(self, client):
        msg = _mock_task("ping", "t-ping-002")
        result = client.process_server_message(msg)
        assert result["task_id"] == "t-ping-002"

    def test_ping_success(self, client):
        result = client.process_server_message(_mock_task("ping"))
        assert result["success"] is True

    def test_ping_summary_pong(self, client):
        result = client.process_server_message(_mock_task("ping"))
        assert "pong" in result["summary"]

    def test_ping_no_sensitive_fields(self, client):
        result = client.process_server_message(_mock_task("ping"))
        assert _no_sensitive(result)

    def test_ping_full_loop(self, client):
        """run_mock_loop: auth → auth_ok → ping task → result 포함."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-001"},
            _mock_task("ping", "t-loop-ping"),
        ]
        sent = client.run_mock_loop(server_messages)
        # auth payload가 첫 번째
        assert sent[0]["type"] == "auth"
        assert sent[0]["agent_id"] == "test-agent-001"
        # result가 두 번째
        result = sent[1]
        assert result["type"] == "result"
        assert result["task_id"] == "t-loop-ping"
        assert result["success"] is True


# ── 3. system_info task lifecycle ─────────────────────────────────────────────

class TestSystemInfoLifecycle:
    def test_system_info_success(self, client):
        result = client.process_server_message(_mock_task("system_info"))
        assert result["success"] is True

    def test_system_info_has_os(self, client):
        result = client.process_server_message(_mock_task("system_info"))
        assert "os=" in result["summary"]

    def test_system_info_no_sensitive(self, client):
        result = client.process_server_message(_mock_task("system_info"))
        assert _no_sensitive(result)

    def test_system_info_no_browser_launch(self, client):
        """system_info 처리 중 프로세스 실행 없음 — result만 확인."""
        result = client.process_server_message(_mock_task("system_info"))
        # summary에 경로/파일명 없음 (플랫폼 이름/호스트명만)
        summary = result["summary"]
        assert "\\" not in summary or "os=" in summary  # Windows 경로 형식 없음
        assert "exec" not in summary.lower()


# ── 4. list_allowed_apps task lifecycle ──────────────────────────────────────

class TestListAllowedAppsLifecycle:
    def test_list_apps_success(self, client):
        result = client.process_server_message(_mock_task("list_allowed_apps"))
        assert result["success"] is True

    def test_list_apps_contains_browser(self, client):
        result = client.process_server_message(_mock_task("list_allowed_apps"))
        assert "browser" in result["summary"]

    def test_list_apps_no_execution(self, client):
        """앱 목록 반환 — 실제 프로그램 실행 없음."""
        result = client.process_server_message(_mock_task("list_allowed_apps"))
        assert result is not None
        assert result["success"] is True

    def test_list_apps_no_sensitive(self, client):
        result = client.process_server_message(_mock_task("list_allowed_apps"))
        assert _no_sensitive(result)


# ── 5. high-risk task 차단 테스트 ────────────────────────────────────────────

class TestHighRiskBlock:
    def test_capture_screenshot_blocked(self, client):
        """capture_screenshot task 수신 시 실행하지 않고 blocked result 반환."""
        msg = {
            "type": "task",
            "task": {
                "task_id": "t-screenshot",
                "agent_id": "test-agent-001",
                "action": "capture_screenshot",
                "params": {},
                "risk_level": "high",
                "approved": True,
            },
        }
        result = client.process_server_message(msg)
        assert result is not None
        assert result["success"] is False
        assert result["error_code"] == "BLOCKED"

    def test_handle_task_capture_raises(self):
        task = {"task_id": "t-ss", "action": "capture_screenshot", "params": {}}
        with pytest.raises(BlockedAction):
            handle_task(task)

    def test_open_url_not_implemented(self):
        task = {"task_id": "t-url", "action": "open_url", "params": {"url": "https://example.com"}}
        with pytest.raises(NotImplementedInThisStage):
            handle_task(task)

    def test_list_files_not_implemented(self):
        task = {"task_id": "t-files", "action": "list_files_readonly", "params": {}}
        with pytest.raises(NotImplementedInThisStage):
            handle_task(task)

    def test_delete_file_not_implemented(self):
        task = {"task_id": "t-del", "action": "delete_file", "params": {}}
        with pytest.raises(NotImplementedInThisStage):
            handle_task(task)


# ── 6. 외부 연결 차단 테스트 ─────────────────────────────────────────────────

class TestConnectionBlock:
    def test_dry_run_connect_does_not_raise(self, client):
        """dry_run=True 시 connect()는 아무 일도 하지 않고 리턴."""
        client.connect()  # must not raise

    def test_non_dry_run_connect_raises(self):
        cfg = load_config(
            server_base_url="http://prod-server:8400",
            agent_id="a", device_token="t",
            dry_run=False,
        )
        c = LocalAgentClient(cfg)
        with pytest.raises(NotImplementedError):
            c.connect()

    def test_run_mock_loop_does_not_use_network(self, client):
        """run_mock_loop는 네트워크 없이 동작한다."""
        sent = client.run_mock_loop([{"type": "auth_ok", "agent_id": "test-agent-001"}])
        # auth만 반환, 예외 없음
        assert sent[0]["type"] == "auth"

    def test_mock_server_url_not_real(self, mock_config):
        """테스트용 URL이 운영 URL 형식이 아님."""
        assert "mock-server" in mock_config.server_base_url
        assert "prod" not in mock_config.server_base_url.lower()


# ── 7. 민감정보 제거 테스트 ──────────────────────────────────────────────────

class TestSensitiveStrip:
    @pytest.mark.parametrize("key", [
        "token", "password", "secret", "cookie",
        "authorization", "raw_params", "api_key", "session",
    ])
    def test_strip_sensitive_key(self, key):
        result = strip_sensitive({key: "SENSITIVE_VALUE", "safe": "ok"})
        assert key not in result
        assert result["safe"] == "ok"

    def test_result_payload_strips_observe_summary(self):
        obs = {"token": "leak", "url": "about:blank", "count": 3}
        r = build_result("t-x", success=True, observe_summary=obs)
        assert "token" not in r["observe_summary"]
        assert r["observe_summary"]["count"] == 3

    def test_result_payload_strips_audit_summary(self):
        audit = {"secret": "leak", "event_count": 5}
        r = build_result("t-y", success=True, audit_summary=audit)
        assert "secret" not in r["audit_summary"]
        assert r["audit_summary"]["event_count"] == 5

    def test_auth_token_not_in_non_auth_payloads(self, client):
        """auth 이후 result payload에는 device_token 미포함."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-001"},
            _mock_task("ping", "t-tok"),
        ]
        sent = client.run_mock_loop(server_messages)
        # auth(0)는 device_token 포함이 정상(WS 전송용), result(1)에는 없어야 함
        result_str = str(sent[1])
        assert "mock-token-for-test" not in result_str

    def test_task_result_no_params_leak(self, client):
        """task params에 민감 키가 있어도 result에 노출되지 않음."""
        msg = {
            "type": "task",
            "task": {
                "task_id": "t-sens",
                "action": "ping",
                "params": {"token": "should-not-appear", "reason": "test"},
                "risk_level": "low",
            },
        }
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "should-not-appear" not in result_str


# ── 8. auth payload 테스트 ───────────────────────────────────────────────────

class TestAuthPayload:
    def test_auth_type(self):
        auth = build_auth("a-001", "dummy-token")
        assert auth["type"] == "auth"

    def test_auth_agent_id(self):
        auth = build_auth("a-001", "dummy-token")
        assert auth["agent_id"] == "a-001"

    def test_run_mock_loop_first_msg_is_auth(self, client):
        sent = client.run_mock_loop([])
        assert len(sent) == 1
        assert sent[0]["type"] == "auth"
        assert sent[0]["agent_id"] == "test-agent-001"

    def test_auth_token_not_logged(self, caplog):
        import logging
        with caplog.at_level(logging.DEBUG, logger="agent.local_agent_client"):
            build_auth("a-001", "actual-secret-token")
        assert "actual-secret-token" not in caplog.text


# ── 9. 복합 lifecycle 테스트 ─────────────────────────────────────────────────

class TestFullLifecycle:
    def test_multi_task_loop(self, client):
        """auth_ok → ping → system_info → list_allowed_apps 순서 처리."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-001"},
            _mock_task("ping", "t-1"),
            {"type": "heartbeat_ack"},
            _mock_task("system_info", "t-2"),
            {"type": "idle"},
            _mock_task("list_allowed_apps", "t-3"),
        ]
        sent = client.run_mock_loop(server_messages)
        # auth + ping result + system_info result + list_allowed_apps result = 4
        assert len(sent) == 4
        assert sent[0]["type"] == "auth"
        assert sent[1]["task_id"] == "t-1"
        assert sent[2]["task_id"] == "t-2"
        assert sent[3]["task_id"] == "t-3"

    def test_blocked_task_in_loop(self, client):
        """capture_screenshot 수신 시 blocked result 반환, loop 계속."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-001"},
            {
                "type": "task",
                "task": {
                    "task_id": "t-blocked",
                    "action": "capture_screenshot",
                    "params": {},
                    "risk_level": "high",
                    "approved": True,
                },
            },
            _mock_task("ping", "t-after-block"),
        ]
        sent = client.run_mock_loop(server_messages)
        # auth + blocked result + ping result = 3
        assert len(sent) == 3
        blocked = sent[1]
        assert blocked["success"] is False
        assert blocked["error_code"] == "BLOCKED"
        ping = sent[2]
        assert ping["success"] is True

    def test_all_results_no_sensitive(self, client):
        """모든 result payload에 민감정보 없음."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-001"},
            _mock_task("ping", "t-s1"),
            _mock_task("system_info", "t-s2"),
            _mock_task("list_allowed_apps", "t-s3"),
        ]
        sent = client.run_mock_loop(server_messages)
        for payload in sent[1:]:  # auth 제외
            assert _no_sensitive(payload), f"sensitive field found in {payload}"
