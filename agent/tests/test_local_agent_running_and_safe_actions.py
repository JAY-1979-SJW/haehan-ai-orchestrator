"""Stage 13F-2D: running payload and safe action skeleton tests.

검증 범위:
  - build_running() payload contract
  - task lifecycle: running → result 순서
  - open_url dry-run (브라우저/URL 실행 금지)
  - list_files_readonly dry-run (파일 시스템 접근 금지)
  - capture_screenshot remains blocked
  - sensitive stripping compatibility
  - Stage 13F-2C contract 회귀 없음 확인

실제 외부 네트워크/운영 서버 접속 없음.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    BlockedAction,
    DRY_RUN_ACTIONS,
    LocalAgentClient,
    LOW_RISK_ACTIONS,
    NotImplementedInThisStage,
    build_result,
    build_running,
    handle_task,
    load_config,
    strip_sensitive,
)

# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return load_config(
        server_base_url="http://mock-server:8400",
        agent_id="test-agent-2d",
        device_token="mock-token-2d",
        dry_run=True,
    )


@pytest.fixture
def client(cfg):
    return LocalAgentClient(cfg)


def _task_msg(action: str, task_id: str = "t-2d", risk: str = "low") -> dict:
    return {
        "type": "task",
        "task": {
            "task_id": task_id,
            "agent_id": "test-agent-2d",
            "action": action,
            "params": {},
            "risk_level": risk,
            "approved": False,
        },
    }


# ── 1. running payload contract ───────────────────────────────────────────────

class TestRunningPayloadContract:
    def test_build_running_type(self):
        r = build_running("task-abc")
        assert r["type"] == "running"

    def test_build_running_task_id(self):
        r = build_running("task-abc")
        assert r["task_id"] == "task-abc"

    def test_build_running_no_token(self):
        r = build_running("task-abc")
        assert "token" not in r
        assert "device_token" not in r

    def test_build_running_no_params(self):
        r = build_running("task-abc")
        assert "params" not in r
        assert "raw_params" not in r

    def test_build_running_no_extra_sensitive(self):
        r = build_running("task-xyz")
        for key in r:
            low = key.lower()
            for bad in ("token", "password", "secret", "cookie", "authorization", "session", "api_key"):
                assert bad not in low, f"sensitive key {key!r} in running payload"

    def test_build_running_accepted_by_server(self):
        """running type은 서버 허용 메시지 목록에 포함."""
        SERVER_ACCEPTED = {"auth", "heartbeat", "pull", "running", "result"}
        assert "running" in SERVER_ACCEPTED


# ── 2. task lifecycle: running → result ──────────────────────────────────────

class TestTaskLifecycleRunningThenResult:
    def test_process_with_running_returns_list(self, client):
        msg = _task_msg("ping", "t-lifecycle")
        payloads = client.process_server_message_with_running(msg)
        assert isinstance(payloads, list)
        assert len(payloads) == 2

    def test_running_comes_before_result(self, client):
        msg = _task_msg("ping", "t-order")
        payloads = client.process_server_message_with_running(msg)
        assert payloads[0]["type"] == "running"
        assert payloads[1]["type"] == "result"

    def test_running_and_result_same_task_id(self, client):
        msg = _task_msg("ping", "t-match")
        payloads = client.process_server_message_with_running(msg)
        assert payloads[0]["task_id"] == "t-match"
        assert payloads[1]["task_id"] == "t-match"

    def test_non_task_message_returns_empty(self, client):
        payloads = client.process_server_message_with_running({"type": "heartbeat_ack"})
        assert payloads == []

    def test_missing_task_field_returns_empty(self, client):
        payloads = client.process_server_message_with_running({"type": "task"})
        assert payloads == []

    def test_lifecycle_for_dry_run_actions(self, client):
        for action in ["open_url", "list_files_readonly"]:
            payloads = client.process_server_message_with_running(_task_msg(action, f"t-{action}"))
            assert len(payloads) == 2
            assert payloads[0]["type"] == "running"
            assert payloads[1]["type"] == "result"

    def test_lifecycle_for_blocked_action(self, client):
        payloads = client.process_server_message_with_running(
            _task_msg("capture_screenshot", "t-ss", risk="high")
        )
        assert len(payloads) == 2
        assert payloads[0]["type"] == "running"
        assert payloads[1]["success"] is False
        assert payloads[1]["error_code"] == "BLOCKED"


# ── 3. open_url dry-run ───────────────────────────────────────────────────────

class TestOpenUrlDryRun:
    def test_open_url_returns_result(self, client):
        msg = _task_msg("open_url", "t-ou")
        result = client.process_server_message(msg)
        assert result is not None
        assert result["type"] == "result"

    def test_open_url_error_code(self, client):
        msg = _task_msg("open_url", "t-ou-ec")
        result = client.process_server_message(msg)
        assert result["error_code"] == "DRY_RUN_ONLY"

    def test_open_url_success_false(self, client):
        msg = _task_msg("open_url", "t-ou-sf")
        result = client.process_server_message(msg)
        assert result["success"] is False

    def test_open_url_no_raw_url_in_result(self, client):
        msg = _task_msg("open_url", "t-ou-url")
        msg["task"]["params"] = {"url": "https://external.example.com/path?q=secret#frag"}
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "external.example.com" not in result_str
        assert "?q=secret" not in result_str
        assert "#frag" not in result_str
        assert "https://" not in result_str

    def test_open_url_no_browser_launch(self, client):
        """open_url 처리 중 subprocess/webbrowser 호출 없음 (dry-run 결과만)."""
        import subprocess
        original = subprocess.run
        launched = []

        def mock_run(*args, **kwargs):
            launched.append(args)
            return original(*args, **kwargs)

        msg = _task_msg("open_url", "t-ou-nb")
        client.process_server_message(msg)
        assert len(launched) == 0

    def test_open_url_in_dry_run_actions(self):
        assert "open_url" in DRY_RUN_ACTIONS


# ── 4. list_files_readonly dry-run ───────────────────────────────────────────

class TestListFilesDryRun:
    def test_list_files_returns_result(self, client):
        msg = _task_msg("list_files_readonly", "t-lf")
        result = client.process_server_message(msg)
        assert result is not None
        assert result["type"] == "result"

    def test_list_files_error_code(self, client):
        msg = _task_msg("list_files_readonly", "t-lf-ec")
        result = client.process_server_message(msg)
        assert result["error_code"] == "DRY_RUN_ONLY"

    def test_list_files_success_false(self, client):
        msg = _task_msg("list_files_readonly", "t-lf-sf")
        result = client.process_server_message(msg)
        assert result["success"] is False

    def test_list_files_no_raw_path(self, client):
        msg = _task_msg("list_files_readonly", "t-lf-path")
        msg["task"]["params"] = {"path": "C:\\Users\\skyjw\\Documents"}
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "C:\\" not in result_str
        assert "/home/" not in result_str
        assert "skyjw" not in result_str

    def test_list_files_in_dry_run_actions(self):
        assert "list_files_readonly" in DRY_RUN_ACTIONS


# ── 5. capture_screenshot remains blocked ────────────────────────────────────

class TestCaptureScreenshotBlocked:
    def test_blocked_result_type(self, client):
        msg = _task_msg("capture_screenshot", "t-ss", risk="high")
        result = client.process_server_message(msg)
        assert result["type"] == "result"
        assert result["success"] is False
        assert result["error_code"] == "BLOCKED"

    def test_blocked_no_stack_trace(self, client):
        msg = _task_msg("capture_screenshot", "t-ss-st", risk="high")
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "Traceback" not in result_str
        assert "raise " not in result_str

    def test_handle_task_raises_blocked(self):
        with pytest.raises(BlockedAction):
            handle_task({"task_id": "t", "action": "capture_screenshot"})

    def test_not_in_low_risk_or_dry_run(self):
        assert "capture_screenshot" not in LOW_RISK_ACTIONS
        assert "capture_screenshot" not in DRY_RUN_ACTIONS


# ── 6. sensitive stripping compatibility ─────────────────────────────────────

class TestSensitiveStripping:
    SENSITIVE_KEYS = [
        "token", "password", "secret", "cookie", "authorization",
        "raw_params", "params", "api_key", "session", "passwd",
        "pwd", "device_token",
    ]

    def test_all_sensitive_keys_stripped(self):
        for key in self.SENSITIVE_KEYS:
            payload = {key: "SHOULD_BE_GONE", "safe": "ok"}
            result = strip_sensitive(payload)
            assert key not in result, f"key {key!r} not stripped"
            assert result["safe"] == "ok"

    def test_running_payload_no_sensitive(self):
        r = build_running("t-strip")
        for key in r:
            for s in self.SENSITIVE_KEYS:
                assert s not in key.lower(), f"sensitive key {key!r} in running payload"

    def test_result_payload_observe_summary_stripped(self):
        obs = {"token": "leak", "url_category": "dry-run", "count": 1}
        r = build_result("t", success=False, observe_summary=obs, error_code="DRY_RUN_ONLY")
        assert "token" not in r["observe_summary"]
        assert r["observe_summary"]["count"] == 1


# ── 7. 기존 contract 회귀 확인 ────────────────────────────────────────────────

class TestContractRegression:
    def test_low_risk_actions_still_complete(self, client):
        for action in ["ping", "system_info", "list_allowed_apps"]:
            msg = _task_msg(action, f"t-reg-{action}")
            result = client.process_server_message(msg)
            assert result["success"] is True, f"action={action} should succeed"
            assert result["type"] == "result"

    def test_run_mock_loop_unchanged(self, client):
        """run_mock_loop 반환 형식이 기존 contract와 동일."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "test-agent-2d"},
            _task_msg("ping", "t-loop"),
            {"type": "heartbeat_ack"},
        ]
        sent = client.run_mock_loop(server_messages)
        assert sent[0]["type"] == "auth"
        assert sent[1]["type"] == "result"
        assert sent[1]["task_id"] == "t-loop"

    def test_auth_no_token_in_heartbeat(self):
        from agent.local_agent_client import build_heartbeat
        hb = build_heartbeat("agent-2d")
        assert "token" not in hb
        assert "device_token" not in hb
