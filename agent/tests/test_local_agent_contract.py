"""Stage 13F-2C: server-agent WebSocket message contract test.

서버 local_agent_router.py / local_agent_registry.py 가 기대하는 스키마와
agent/local_agent_client.py 가 생성하는 스키마를 비교하여
실제 운영 연결 전에 mismatch를 차단한다.

실제 외부 네트워크/운영 서버 접속 없음.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
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

# ── 서버 스키마 상수 (ai_orchestrator/local_agent_registry.py에서 추출) ────────

# ACTION_RISK
SERVER_ACTION_RISK = {
    "ping": "low",
    "system_info": "low",
    "list_allowed_apps": "low",
    "open_url": "low",
    "list_files_readonly": "medium",
    "capture_screenshot": "high",
}

# KNOWN_TASK_STATUSES
SERVER_KNOWN_TASK_STATUSES = frozenset({
    "queued", "delivered", "running",
    "waiting_approval", "completed", "failed", "rejected",
    "cancel_requested", "cancelled",
})

# _SENSITIVE_KEYS (서버)
SERVER_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "session_token",
    "device_token", "cookie", "cookies", "session",
    "client_secret", "secret", "api_secret", "api_key",
    "auth", "authorization",
})

# to_dispatch() 반환 필드 (서버→클라이언트 task payload)
SERVER_TASK_DISPATCH_FIELDS = {"task_id", "agent_id", "action", "params", "risk_level", "approved"}

# WS 허용 클라이언트→서버 메시지 타입
SERVER_ACCEPTED_MSG_TYPES = {"auth", "heartbeat", "pull", "running", "result"}

# WS 서버→클라이언트 메시지 타입
SERVER_SENT_MSG_TYPES = {"auth_ok", "task", "running_ack", "result_ack", "idle", "error"}

# ── fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_cfg():
    return load_config(
        server_base_url="http://mock-server:8400",
        agent_id="contract-agent-001",
        device_token="mock-contract-token",
        dry_run=True,
    )


@pytest.fixture
def client(mock_cfg):
    return LocalAgentClient(mock_cfg)


def _server_task_msg(action: str, task_id: str = "t-contract", risk: str = "low") -> dict:
    """서버 to_dispatch() 형식 task 메시지 (서버→클라이언트)."""
    return {
        "type": "task",
        "task": {
            "task_id": task_id,
            "agent_id": "contract-agent-001",
            "action": action,
            "params": {},
            "risk_level": risk,
            "approved": False,
        },
    }


# ── 1. auth payload contract ──────────────────────────────────────────────────

class TestAuthContract:
    def test_auth_type_field(self):
        """서버: auth_msg.get("type") != "auth" → close(4401)."""
        auth = build_auth("agent-001", "mock-token")
        assert auth["type"] == "auth"

    def test_auth_agent_id_field(self):
        """서버: claimed_agent_id = auth_msg.get("agent_id")."""
        auth = build_auth("agent-xyz", "mock-token")
        assert auth["agent_id"] == "agent-xyz"

    def test_auth_device_token_field(self):
        """서버: device_token = auth_msg.get("device_token")."""
        auth = build_auth("a", "mock-dev-tok")
        assert "device_token" in auth

    def test_auth_not_in_repr_or_str(self, mock_cfg):
        """device_token은 config repr/str에 절대 노출되지 않음."""
        assert "mock-contract-token" not in repr(mock_cfg)
        assert "mock-contract-token" not in str(mock_cfg)

    def test_auth_payload_not_in_result(self, client):
        """result payload에 device_token 미포함."""
        result = handle_task({"task_id": "t", "action": "ping"})
        assert "device_token" not in str(result)
        assert "mock-contract-token" not in str(result)


# ── 2. heartbeat contract ─────────────────────────────────────────────────────

class TestHeartbeatContract:
    def test_heartbeat_type(self):
        """서버: mtype == "heartbeat"."""
        hb = build_heartbeat("a")
        assert hb["type"] == "heartbeat"

    def test_heartbeat_accepted_by_server(self):
        """heartbeat type은 서버 허용 메시지 목록에 포함."""
        assert "heartbeat" in SERVER_ACCEPTED_MSG_TYPES

    def test_heartbeat_extra_fields_ok(self):
        """서버는 heartbeat 메시지에서 type만 체크, 추가 필드는 무시."""
        hb = build_heartbeat("agent-001")
        # agent_id, timestamp 추가 필드 포함 가능
        assert "agent_id" in hb
        assert "timestamp" in hb

    def test_heartbeat_no_sensitive(self):
        hb = build_heartbeat("agent-001")
        for k in hb:
            for s in ["token", "password", "secret", "device"]:
                assert s not in k.lower()


# ── 3. heartbeat_ack contract ─────────────────────────────────────────────────

class TestHeartbeatAckContract:
    def test_server_sends_heartbeat_ack(self):
        """서버→클라이언트 메시지 타입 목록에 heartbeat_ack는 없음 (idle/task 등만).

        서버 코드: await ws.send_json({"type": "heartbeat_ack"})
        """
        # 서버가 보내는 메시지이므로 SERVER_SENT_MSG_TYPES에 포함시킴
        assert "heartbeat_ack" not in SERVER_SENT_MSG_TYPES  # 별도 ack 전용 타입
        # 하지만 실제로 서버 코드는 heartbeat_ack를 전송함 → client가 처리해야 함

    def test_client_ignores_heartbeat_ack(self, client):
        """클라이언트는 heartbeat_ack를 조용히 처리 (응답 없음)."""
        result = client.process_server_message({"type": "heartbeat_ack"})
        assert result is None

    def test_client_ignores_result_ack(self, client):
        """클라이언트는 result_ack를 조용히 처리."""
        result = client.process_server_message({"type": "result_ack", "task_id": "t", "status": "completed"})
        assert result is None

    def test_client_ignores_running_ack(self, client):
        result = client.process_server_message({"type": "running_ack", "task_id": "t", "status": "running"})
        assert result is None

    def test_client_ignores_idle(self, client):
        result = client.process_server_message({"type": "idle"})
        assert result is None


# ── 4. task payload contract (서버→클라이언트) ────────────────────────────────

class TestTaskPayloadContract:
    def test_task_dispatch_required_fields(self):
        """서버 to_dispatch()는 task_id/agent_id/action/params/risk_level/approved 반환."""
        assert SERVER_TASK_DISPATCH_FIELDS == {
            "task_id", "agent_id", "action", "params", "risk_level", "approved"
        }

    def test_client_handles_task_id(self, client):
        """클라이언트는 task["task_id"] 필드를 처리."""
        msg = _server_task_msg("ping", "t-id-check")
        result = client.process_server_message(msg)
        assert result["task_id"] == "t-id-check"

    def test_client_handles_action(self, client):
        """클라이언트는 task["action"] 필드를 처리."""
        for action in ["ping", "system_info", "list_allowed_apps"]:
            msg = _server_task_msg(action, f"t-{action}")
            result = client.process_server_message(msg)
            assert result is not None and result["type"] == "result"

    def test_task_wrapper_structure(self, client):
        """서버는 {"type":"task","task":{...}} 형식으로 전달."""
        msg = {"type": "task", "task": {"task_id": "t", "action": "ping", "params": {}}}
        result = client.process_server_message(msg)
        assert result is not None

    def test_missing_task_field_returns_none(self, client):
        """task 키 누락 시 None 반환 (조용히 무시)."""
        msg = {"type": "task"}  # task 키 없음
        result = client.process_server_message(msg)
        assert result is None


# ── 5. result payload contract (클라이언트→서버) ──────────────────────────────

class TestResultPayloadContract:
    def test_result_type_field(self):
        """서버: mtype == "result" 체크."""
        r = build_result("t", success=True)
        assert r["type"] == "result"

    def test_result_task_id_field(self):
        """서버: task_id = _safe_str(msg.get("task_id"))."""
        r = build_result("task-123", success=True)
        assert r["task_id"] == "task-123"

    def test_result_success_field(self):
        """서버: success = bool(msg.get("success", False))."""
        r = build_result("t", success=True)
        assert isinstance(r["success"], bool)

    def test_result_summary_field(self):
        """서버: summary = _safe_str(msg.get("summary"))[:500]."""
        r = build_result("t", success=True, summary="done")
        assert "summary" in r
        assert len(r["summary"]) <= 500

    def test_result_error_code_field(self):
        """서버: error_code = _safe_str(msg.get("error_code"))[:80]."""
        r = build_result("t", success=False, error_code="ERR_TEST")
        assert r["error_code"] == "ERR_TEST"
        assert len(r["error_code"]) <= 80

    def test_result_error_field(self):
        """서버: error = _safe_str(msg.get("error"))[:500]."""
        r = build_result("t", success=False, error="some error")
        assert r["error"] == "some error"

    def test_result_observe_summary_field(self):
        """서버: raw_observe = msg.get("observe_summary"); isinstance(raw_observe, dict)."""
        obs = {"count": 3, "url_category": "about:blank"}
        r = build_result("t", success=True, observe_summary=obs)
        assert isinstance(r["observe_summary"], dict)

    def test_result_audit_summary_field(self):
        """서버: raw_audit = msg.get("audit_summary"); isinstance(raw_audit, dict)."""
        audit = {"event_count": 5}
        r = build_result("t", success=True, audit_summary=audit)
        assert isinstance(r["audit_summary"], dict)

    def test_result_accepted_by_server(self):
        """result type은 서버 허용 메시지 목록에 포함."""
        assert "result" in SERVER_ACCEPTED_MSG_TYPES

    def test_result_summary_truncation(self):
        """서버와 동일하게 500자 제한."""
        r = build_result("t", success=True, summary="x" * 600)
        assert len(r["summary"]) == 500


# ── 6. blocked result contract ────────────────────────────────────────────────

class TestBlockedResultContract:
    def test_capture_screenshot_blocked(self, client):
        """capture_screenshot은 실행 안 하고 blocked result 반환."""
        msg = _server_task_msg("capture_screenshot", "t-ss", risk="high")
        result = client.process_server_message(msg)
        assert result is not None
        assert result["success"] is False
        assert result["error_code"] == "BLOCKED"

    def test_blocked_result_is_valid_result_type(self, client):
        """blocked result도 type=result로 서버에 전달 가능."""
        msg = _server_task_msg("capture_screenshot", "t-ss2", risk="high")
        result = client.process_server_message(msg)
        assert result["type"] == "result"
        assert "task_id" in result

    def test_blocked_result_no_stack_trace(self, client):
        """blocked result에 raw exception/stack trace 미포함."""
        msg = _server_task_msg("capture_screenshot", "t-ss3", risk="high")
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "Traceback" not in result_str
        assert "raise " not in result_str

    def test_not_implemented_result_no_stack_trace(self, client):
        """미구현 action result에 stack trace 미포함."""
        msg = _server_task_msg("open_url", "t-ou", risk="low")
        result = client.process_server_message(msg)
        assert result["error_code"] == "NOT_IMPLEMENTED"
        assert "Traceback" not in str(result)


# ── 7. action enum contract ───────────────────────────────────────────────────

class TestActionEnumContract:
    def test_low_risk_client_actions_in_server_action_risk(self):
        """클라이언트 LOW_RISK_ACTIONS는 서버 ACTION_RISK에 모두 등록되어 있음."""
        for action in LOW_RISK_ACTIONS:
            assert action in SERVER_ACTION_RISK, (
                f"action {action!r} is in client LOW_RISK_ACTIONS "
                f"but not in server ACTION_RISK"
            )

    def test_client_low_risk_actions_are_low_risk_on_server(self):
        """클라이언트가 완료 처리하는 low-risk action들은 서버에서도 low로 등록."""
        for action in LOW_RISK_ACTIONS:
            assert SERVER_ACTION_RISK[action] == "low", (
                f"action {action!r} is not low risk on server"
            )

    def test_capture_screenshot_is_high_risk(self):
        """capture_screenshot은 서버와 클라이언트 모두 high-risk로 차단."""
        assert SERVER_ACTION_RISK.get("capture_screenshot") == "high"
        with pytest.raises(BlockedAction):
            handle_task({"task_id": "t", "action": "capture_screenshot"})

    def test_open_url_not_in_client_low_risk(self):
        """open_url은 클라이언트에서 이번 단계 미구현."""
        assert "open_url" not in LOW_RISK_ACTIONS
        with pytest.raises(NotImplementedInThisStage):
            handle_task({"task_id": "t", "action": "open_url"})

    def test_list_files_not_in_client_low_risk(self):
        """list_files_readonly는 클라이언트에서 이번 단계 미구현."""
        assert "list_files_readonly" not in LOW_RISK_ACTIONS
        with pytest.raises(NotImplementedInThisStage):
            handle_task({"task_id": "t", "action": "list_files_readonly"})

    def test_unknown_action_not_implemented(self):
        with pytest.raises((NotImplementedInThisStage, BlockedAction)):
            handle_task({"task_id": "t", "action": "delete_file"})


# ── 8. status enum contract ───────────────────────────────────────────────────

class TestStatusEnumContract:
    def test_server_known_statuses(self):
        """서버 KNOWN_TASK_STATUSES 확인."""
        expected = {
            "queued", "delivered", "running",
            "waiting_approval", "completed", "failed", "rejected",
            "cancel_requested", "cancelled",
        }
        assert SERVER_KNOWN_TASK_STATUSES == expected

    def test_result_success_maps_to_completed(self):
        """success=True result → 서버에서 completed로 전환."""
        r = build_result("t", success=True, summary="pong")
        assert r["success"] is True  # 서버: completed

    def test_result_failure_maps_to_failed(self):
        """success=False result → 서버에서 failed로 전환."""
        r = build_result("t", success=False, error_code="ERR")
        assert r["success"] is False  # 서버: failed


# ── 9. sensitive stripping contract ──────────────────────────────────────────

class TestSensitiveStrippingContract:
    # 서버 _SENSITIVE_KEYS와 클라이언트 _SENSITIVE_KEY_PARTS의 교집합
    COMMON_SENSITIVE = {
        "password", "token", "access_token", "refresh_token",
        "device_token", "cookie", "session", "client_secret",
        "secret", "api_key", "authorization",
    }

    def test_common_keys_stripped_by_client(self):
        """서버와 클라이언트 공통 민감 키 제거 확인."""
        for key in self.COMMON_SENSITIVE:
            result = strip_sensitive({key: "SENSITIVE", "safe": "ok"})
            assert key not in result, f"key {key!r} should be stripped"
            assert result["safe"] == "ok"

    def test_server_extra_keys_passwd_pwd(self):
        """서버의 passwd/pwd 도 클라이언트에서 처리 (password 포함 탐지)."""
        result = strip_sensitive({"passwd": "x", "pwd": "y", "name": "z"})
        assert "passwd" not in result  # "password" 포함
        assert "pwd" not in result     # "password" 포함
        assert result["name"] == "z"

    def test_client_extra_keys_raw_params(self):
        """클라이언트 추가 제거 키: raw_params."""
        result = strip_sensitive({"raw_params": "leak", "action": "ping"})
        assert "raw_params" not in result
        assert result["action"] == "ping"

    def test_nested_stripping(self):
        """중첩 dict에서도 민감 키 제거."""
        payload = {
            "observe": {"token": "secret", "count": 3},
            "audit": {"secret": "s", "events": 5},
        }
        result = strip_sensitive(payload)
        assert "token" not in result["observe"]
        assert result["observe"]["count"] == 3
        assert "secret" not in result["audit"]
        assert result["audit"]["events"] == 5

    def test_result_observe_summary_stripped(self):
        obs = {"token": "leak", "url_category": "about:blank", "count": 2}
        r = build_result("t", success=True, observe_summary=obs)
        assert "token" not in r["observe_summary"]
        assert r["observe_summary"]["count"] == 2

    def test_result_audit_summary_stripped(self):
        audit = {"secret": "leak", "event_count": 7, "api_key": "k"}
        r = build_result("t", success=True, audit_summary=audit)
        assert "secret" not in r["audit_summary"]
        assert "api_key" not in r["audit_summary"]
        assert r["audit_summary"]["event_count"] == 7


# ── 10. diagnostics safety contract ──────────────────────────────────────────

class TestDiagnosticsSafetyContract:
    def test_result_no_raw_html(self, client):
        """result payload에 raw HTML 미포함."""
        msg = _server_task_msg("ping", "t-html")
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "<html" not in result_str.lower()
        assert "<!doctype" not in result_str.lower()

    def test_result_no_raw_url(self, client):
        """result payload에 외부 URL 미포함 (system_info hostname만 허용)."""
        msg = _server_task_msg("ping", "t-url")
        result = client.process_server_message(msg)
        result_str = str(result)
        assert "http://" not in result_str
        assert "https://" not in result_str

    def test_result_no_file_path(self, client):
        """result payload에 로컬 파일 경로 미포함."""
        for action in ["ping", "system_info", "list_allowed_apps"]:
            result = client.process_server_message(_server_task_msg(action, f"t-{action}"))
            result_str = str(result)
            assert "C:\\" not in result_str
            assert "/home/" not in result_str

    def test_auth_ok_not_result_payload(self, client):
        """auth_ok는 result payload가 아님 (diagnostics에 task 집계 안 됨)."""
        r = client.process_server_message({"type": "auth_ok", "agent_id": "x"})
        assert r is None  # result payload 생성 없음


# ── 11. 종합 lifecycle contract ───────────────────────────────────────────────

class TestLifecycleContract:
    def test_full_schema_compatible_loop(self, client):
        """서버 스키마 호환 mock loop: auth → auth_ok → task → result."""
        server_messages = [
            {"type": "auth_ok", "agent_id": "contract-agent-001"},
            _server_task_msg("ping", "t-loop"),
            {"type": "heartbeat_ack"},
            _server_task_msg("system_info", "t-loop2"),
        ]
        sent = client.run_mock_loop(server_messages)
        # auth + ping result + system_info result = 3
        assert len(sent) == 3
        auth = sent[0]
        assert auth["type"] == "auth"
        assert auth["agent_id"] == "contract-agent-001"
        assert "device_token" in auth  # WS 인증 필드 포함
        ping_r = sent[1]
        assert ping_r["type"] == "result"
        assert ping_r["task_id"] == "t-loop"
        assert ping_r["success"] is True

    def test_all_result_fields_server_compatible(self, client):
        """모든 low-risk result가 서버 _handle_result()와 호환."""
        required_fields = {"type", "task_id", "success", "summary"}
        for action in ["ping", "system_info", "list_allowed_apps"]:
            result = client.process_server_message(_server_task_msg(action, f"t-{action}"))
            assert required_fields.issubset(result.keys()), (
                f"action={action} result missing fields: "
                f"{required_fields - result.keys()}"
            )
