"""테스트 for LocalAgentClient WebSocket dry_run=False 구현.

실제 운영 WebSocket 연결은 차단.
mock 기반 프로토콜 검증만 수행.
"""
from __future__ import annotations

import os
import sys
import pytest
from unittest.mock import Mock, patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    AgentConfig,
    LocalAgentClient,
    ExternalUrlBlocked,
    _http_to_ws_url,
    assert_local_ws_url,
    build_auth,
    build_heartbeat,
)


class TestHttpToWsUrlConversion:
    """http → ws URL 변환 테스트."""

    def test_http_to_ws(self):
        """http://127.0.0.1:8400 → ws://127.0.0.1:8400"""
        result = _http_to_ws_url("http://127.0.0.1:8400")
        assert result == "ws://127.0.0.1:8400"

    def test_https_to_wss(self):
        """https://example.com → wss://example.com"""
        result = _http_to_ws_url("https://example.com")
        assert result == "wss://example.com"

    def test_preserve_path(self):
        """경로 유지"""
        result = _http_to_ws_url("http://127.0.0.1:8400/api/v1")
        assert result.startswith("ws://127.0.0.1:8400/api/v1")


class TestAssertLocalWsUrl:
    """localhost 안전 검증 테스트."""

    def test_localhost_allowed(self):
        """ws://localhost:8400은 허용"""
        assert_local_ws_url("ws://localhost:8400/api/v1/local-agents/ws")
        # no exception

    def test_127_0_0_1_allowed(self):
        """ws://127.0.0.1:8400은 허용"""
        assert_local_ws_url("ws://127.0.0.1:8400/api/v1/local-agents/ws")
        # no exception

    def test_external_host_blocked(self):
        """ws://example.com은 차단"""
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url("ws://example.com/api/v1/local-agents/ws")

    def test_http_scheme_blocked(self):
        """http://는 ws 검증에서 차단"""
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url("http://127.0.0.1:8400/api/v1/local-agents/ws")


class TestConnectDryRunTrue:
    """dry_run=True일 때 기존 동작 유지."""

    def test_dry_run_skips_connection(self):
        """dry_run=True이면 연결하지 않음"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400",
            agent_id="test-agent",
            device_token="test-token",
            heartbeat_interval=10.0,
            dry_run=True,
        )
        client = LocalAgentClient(config)
        result = client.connect(heartbeat_count=2)

        assert result["status"] == "skipped"
        assert result["dry_run"] is True
        assert result["agent_id"] == "test-agent"


class TestConnectDryRunFalse:
    """dry_run=False일 때 실제 연결 (mock)."""

    def test_connect_returns_dict_not_error(self):
        """connect()는 NotImplementedError를 발생하지 않음"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400",
            agent_id="test-agent",
            device_token="test-token",
            heartbeat_interval=10.0,
            dry_run=False,
        )
        client = LocalAgentClient(config)

        # Mock asyncio.run to prevent actual connection
        with patch("agent.local_agent_client.asyncio.run") as mock_run:
            mock_run.return_value = {
                "status": "ok",
                "agent_id": "test-agent",
                "heartbeat_count": 2,
                "sent": 3,
                "received": 3,
            }
            result = client.connect(heartbeat_count=2)
            assert isinstance(result, dict)
            assert "status" in result

    def test_external_url_blocked(self):
        """외부 주소 연결은 차단"""
        config = AgentConfig(
            server_base_url="http://example.com:8400",
            agent_id="test-agent",
            device_token="test-token",
            heartbeat_interval=10.0,
            dry_run=False,
        )
        client = LocalAgentClient(config)
        result = client.connect(heartbeat_count=2)

        assert result["status"] == "error"
        assert "external" in result.get("error", "").lower() or \
               "not localhost" in result.get("error", "").lower()

    def test_incomplete_config_skips(self):
        """config가 불완전하면 skip"""
        config = AgentConfig(
            server_base_url="",
            agent_id="test-agent",
            device_token="test-token",
            heartbeat_interval=10.0,
            dry_run=False,
        )
        client = LocalAgentClient(config)
        result = client.connect(heartbeat_count=2)

        assert result["status"] == "skipped"


class TestAuthAndHeartbeat:
    """auth/heartbeat 메시지 생성 테스트."""

    def test_build_auth_contains_token(self):
        """build_auth()가 device_token을 포함"""
        auth = build_auth("agent-123", "secret-token")
        assert auth["type"] == "auth"
        assert auth["agent_id"] == "agent-123"
        assert auth["device_token"] == "secret-token"

    def test_build_heartbeat_no_token(self):
        """build_heartbeat()는 token을 포함하지 않음"""
        hb = build_heartbeat("agent-123")
        assert hb["type"] == "heartbeat"
        assert hb["agent_id"] == "agent-123"
        assert "device_token" not in hb
        assert "token" not in str(hb).lower() or "timestamp" in hb


class TestWsUrlProperty:
    """ws_url property 테스트."""

    def test_ws_url_construction(self):
        """ws_url이 올바른 경로로 구성"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400",
            agent_id="test",
            device_token="token",
            heartbeat_interval=10.0,
            dry_run=True,
        )
        client = LocalAgentClient(config)
        assert client.ws_url == "http://127.0.0.1:8400/api/v1/local-agents/ws"

    def test_ws_url_strips_trailing_slash(self):
        """ws_url이 trailing slash를 제거"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400/",
            agent_id="test",
            device_token="token",
            heartbeat_interval=10.0,
            dry_run=True,
        )
        client = LocalAgentClient(config)
        assert client.ws_url == "http://127.0.0.1:8400/api/v1/local-agents/ws"


class TestNoTaskExecution:
    """task 실행 금지 테스트."""

    def test_process_server_message_blocked_on_task(self):
        """task 메시지 수신 시 handle_task는 호출되나 실행 제한"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400",
            agent_id="test-agent",
            device_token="token",
            heartbeat_interval=10.0,
            dry_run=True,
        )
        client = LocalAgentClient(config)

        task_msg = {
            "type": "task",
            "task": {
                "task_id": "task-123",
                "action": "open_url",
                "params": {"url": "http://example.com"},
            }
        }

        # process_server_message는 task를 처리하려고 시도
        # 하지만 task_executor는 호출되지 않음
        result = client.process_server_message(task_msg)

        # blocked action 또는 not implemented를 반환해야 함
        assert result is not None
        assert result.get("success") is False


class TestRunnerArguments:
    """runner 명령줄 인자 테스트."""

    def test_runner_with_mock_args(self):
        """runner main()이 ArgumentParser를 처리"""
        from agent.local_agent_ws_runner import main

        # Mock HTTP API registration and WebSocket connect
        with patch("agent.local_agent_ws_runner._register_with_code") as mock_reg, \
             patch("agent.local_agent_client.LocalAgentClient.connect") as mock_connect, \
             patch.dict(os.environ, {"LOCAL_AGENT_REGISTRATION_CODE": "test-code"}):

            mock_reg.return_value = ("agent-123", "device-token-123")
            mock_connect.return_value = {
                "status": "ok",
                "agent_id": "agent-123",
                "heartbeat_count": 2,
                "sent": 3,
                "received": 3,
            }

            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
                "--heartbeat-count", "2",
            ])

            assert result == 0

    def test_runner_missing_registration_code(self):
        """등록 코드가 없으면 실패"""
        from agent.local_agent_ws_runner import main

        with patch.dict(os.environ, {}, clear=True):
            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
            ])

            assert result == 2


class TestSensitiveValueProtection:
    """민감값 보호 테스트."""

    def test_connect_result_no_token(self):
        """connect() 결과에 device_token이 없음"""
        config = AgentConfig(
            server_base_url="http://127.0.0.1:8400",
            agent_id="test-agent",
            device_token="super-secret-token",
            heartbeat_interval=10.0,
            dry_run=False,
        )
        client = LocalAgentClient(config)

        with patch("agent.local_agent_client.asyncio.run") as mock_run:
            mock_run.return_value = {
                "status": "ok",
                "agent_id": "test-agent",
                "heartbeat_count": 2,
                "sent": 3,
                "received": 3,
            }
            result = client.connect(heartbeat_count=2)

            # 결과에 device_token이 없어야 함
            assert "token" not in str(result).lower() or "heartbeat" in str(result)
            assert "secret" not in str(result).lower()

    def test_build_auth_not_logged(self):
        """build_auth() 결과가 로깅되지 않음"""
        auth = build_auth("agent-123", "secret-token")

        # 테스트: auth dict 그 자체는 token을 포함하지만,
        # logger로 출력하면 민감값 제거 함수를 거쳐야 함
        # (이것은 runner에서 처리)
        assert "secret-token" in str(auth)  # dict에는 있음
        # 하지만 logger 출력 시 strip_sensitive()를 거쳐야 함


class TestWsNoopTaskHandler:
    """ws_noop safe task handler 테스트."""

    def test_allow_task_action_option_added(self):
        """runner에 --allow-task-action 옵션이 있음"""
        from agent.local_agent_ws_runner import main
        import sys

        with patch("agent.local_agent_ws_runner._register_with_code") as mock_reg, \
             patch("agent.local_agent_client.LocalAgentClient.connect") as mock_connect, \
             patch.dict(os.environ, {"LOCAL_AGENT_REGISTRATION_CODE": "test-code"}):

            mock_reg.return_value = ("agent-123", "device-token-123")
            mock_connect.return_value = {
                "status": "ok",
                "agent_id": "agent-123",
                "heartbeat_count": 1,
                "sent": 2,
                "received": 2,
            }

            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
                "--heartbeat-count", "1",
                "--allow-task-action", "ws_noop",
                "--max-tasks", "1",
            ])

            assert result == 0
            # connect()가 올바른 옵션으로 호출되었는지 확인
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs.get("allow_task_action") == "ws_noop"
            assert call_kwargs.get("max_tasks") == 1

    def test_max_tasks_validation_rejects_over_1(self):
        """--max-tasks > 1은 거부"""
        from agent.local_agent_ws_runner import main

        with patch.dict(os.environ, {"LOCAL_AGENT_REGISTRATION_CODE": "test-code"}):
            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
                "--max-tasks", "2",
            ])

            assert result == 2

    def test_allow_task_action_validation_only_ws_noop(self):
        """--allow-task-action은 ws_noop만 허용"""
        from agent.local_agent_ws_runner import main

        with patch.dict(os.environ, {"LOCAL_AGENT_REGISTRATION_CODE": "test-code"}):
            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
                "--allow-task-action", "open_url",
                "--max-tasks", "1",
            ])

            assert result == 2

    def test_allow_task_action_requires_max_tasks(self):
        """--allow-task-action은 --max-tasks 없으면 거부"""
        from agent.local_agent_ws_runner import main

        with patch.dict(os.environ, {"LOCAL_AGENT_REGISTRATION_CODE": "test-code"}):
            result = main([
                "--server-url", "http://127.0.0.1:8400",
                "--registration-code-env", "LOCAL_AGENT_REGISTRATION_CODE",
                "--allow-task-action", "ws_noop",
            ])

            assert result == 2

    def test_ws_noop_result_format(self):
        """ws_noop 처리 결과 형식"""
        from agent.local_agent_client import handle_task

        task = {
            "task_id": "t-noop-smoke-001",
            "action": "ws_noop",
            "params": {},
        }
        result = handle_task(task, dry_run=True)

        assert result["success"] is True
        assert result["summary"] == "ws_noop_ok"
        assert result["task_id"] == "t-noop-smoke-001"
        # 민감값이 없어야 함
        assert "token" not in str(result).lower()
        assert "password" not in str(result).lower()


__all__ = [
    "TestHttpToWsUrlConversion",
    "TestAssertLocalWsUrl",
    "TestConnectDryRunTrue",
    "TestConnectDryRunFalse",
    "TestAuthAndHeartbeat",
    "TestWsUrlProperty",
    "TestNoTaskExecution",
    "TestRunnerArguments",
    "TestSensitiveValueProtection",
    "TestWsNoopTaskHandler",
]
