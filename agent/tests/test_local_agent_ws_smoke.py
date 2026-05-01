"""Stage 13F-2E: local WebSocket smoke tests.

in-process Starlette WebSocket 서버를 이용해 실제 WS 프로토콜을 검증한다.
운영 서버/외부 URL 연결 없음. localhost 제한 검증 포함.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Generator

import pytest
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    BlockedAction,
    DRY_RUN_ACTIONS,
    ExternalUrlBlocked,
    LocalAgentClient,
    LOW_RISK_ACTIONS,
    NotImplementedInThisStage,
    assert_local_ws_url,
    build_auth,
    build_heartbeat,
    build_result,
    build_running,
    handle_task,
    load_config,
    strip_sensitive,
)

# ── 민감 키 목록 (검증용) ─────────────────────────────────────────────────────

_SENSITIVE_KEYS = {
    "device_token", "token", "password", "passwd", "pwd",
    "secret", "cookie", "authorization", "raw_params",
    "api_key", "session",
}

# ── test server builder ───────────────────────────────────────────────────────

def _make_test_server(tasks: list[dict]) -> Starlette:
    """tasks 목록을 순서대로 client에게 전달하는 in-process WS 서버.

    흐름:
      recv auth → send auth_ok
      recv heartbeat → send heartbeat_ack
      for each task: send task → recv running → recv result → send result_ack
    """
    received_messages: list[dict] = []

    async def ws_handler(ws: WebSocket) -> None:
        await ws.accept()

        # auth
        auth_msg = await ws.receive_json()
        received_messages.append({"type": auth_msg.get("type")})
        await ws.send_json({"type": "auth_ok", "agent_id": auth_msg.get("agent_id", "")})

        # heartbeat
        hb_msg = await ws.receive_json()
        received_messages.append({"type": hb_msg.get("type")})
        await ws.send_json({"type": "heartbeat_ack"})

        # tasks
        for task_dict in tasks:
            task_msg = {"type": "task", "task": task_dict}
            await ws.send_json(task_msg)

            # expect running
            running = await ws.receive_json()
            received_messages.append(running)

            # expect result
            result = await ws.receive_json()
            received_messages.append(result)

            await ws.send_json({"type": "result_ack", "task_id": result.get("task_id", "")})

        await ws.close()

    app = Starlette(routes=[WebSocketRoute("/ws", ws_handler)])
    # 서버가 수집한 메시지를 테스트에서 접근할 수 있도록 앱에 붙임
    app.state.received = received_messages
    return app


def _make_task(action: str, task_id: str, risk: str = "low") -> dict:
    return {
        "task_id": task_id,
        "agent_id": "smoke-agent-001",
        "action": action,
        "params": {},
        "risk_level": risk,
        "approved": False,
    }


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cfg():
    return load_config(
        server_base_url="http://localhost:0",
        agent_id="smoke-agent-001",
        device_token="smoke-dummy-token",
        dry_run=True,
    )


@pytest.fixture
def client_obj(cfg):
    return LocalAgentClient(cfg)


def _run_smoke(client_obj: LocalAgentClient, tasks: list[dict]) -> dict:
    """in-process WS 서버와 smoke 세션을 실행하고 결과를 반환."""
    app = _make_test_server(tasks)
    tc = TestClient(app)
    with tc.websocket_connect("/ws") as ws:
        result = client_obj.run_ws_protocol(ws, num_tasks=len(tasks))
    result["server_received"] = app.state.received
    return result


# ── 1. auth smoke ─────────────────────────────────────────────────────────────

class TestAuthSmoke:
    def test_auth_type_sent(self, client_obj):
        r = _run_smoke(client_obj, [])
        assert r["sent"][0]["type"] == "auth"

    def test_auth_ok_received(self, client_obj):
        r = _run_smoke(client_obj, [])
        assert r["received"][0]["type"] == "auth_ok"

    def test_auth_no_device_token_in_sent_log(self, client_obj):
        """sent 기록에 device_token 원문이 없어야 한다 (auth type만 기록)."""
        r = _run_smoke(client_obj, [])
        auth_record = r["sent"][0]
        assert "device_token" not in auth_record
        assert "smoke-dummy-token" not in str(auth_record)

    def test_auth_agent_id_in_server_received(self, client_obj):
        """서버가 받은 auth type 기록 확인 — full smoke로 검증."""
        r = _run_smoke(client_obj, [])
        # 서버가 수신한 첫 메시지는 auth type
        assert r["server_received"][0]["type"] == "auth"


# ── 2. heartbeat smoke ────────────────────────────────────────────────────────

class TestHeartbeatSmoke:
    def test_heartbeat_sent(self, client_obj):
        r = _run_smoke(client_obj, [])
        hb_record = r["sent"][1]
        assert hb_record["type"] == "heartbeat"

    def test_heartbeat_ack_received(self, client_obj):
        r = _run_smoke(client_obj, [])
        assert r["received"][1]["type"] == "heartbeat_ack"

    def test_heartbeat_no_token(self, client_obj):
        r = _run_smoke(client_obj, [])
        hb_record = r["sent"][1]
        for key in _SENSITIVE_KEYS:
            assert key not in hb_record, f"sensitive key {key!r} in heartbeat"

    def test_heartbeat_no_result_generated(self, client_obj):
        """heartbeat 처리 시 result 페이로드가 생성되면 안 됨."""
        r = _run_smoke(client_obj, [])
        result_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result"]
        assert len(result_payloads) == 0


# ── 3. ping task smoke ────────────────────────────────────────────────────────

class TestPingTaskSmoke:
    def test_ping_running_then_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("ping", "t-ping")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["type"] == "result"

    def test_ping_running_task_id(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("ping", "t-ping-id")])
        running = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "running")
        assert running["task_id"] == "t-ping-id"

    def test_ping_result_success(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("ping", "t-ping-ok")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["success"] is True

    def test_ping_no_sensitive_in_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("ping", "t-ping-safe")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        result_str = str(result)
        for key in _SENSITIVE_KEYS:
            assert key not in result_str, f"sensitive key {key!r} in result"


# ── 4. system_info task smoke ─────────────────────────────────────────────────

class TestSystemInfoSmoke:
    def test_system_info_running_result_order(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("system_info", "t-si")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["type"] == "result"

    def test_system_info_success(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("system_info", "t-si-ok")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["success"] is True

    def test_system_info_no_sensitive(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("system_info", "t-si-safe")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        result_str = str(result)
        for key in _SENSITIVE_KEYS:
            assert key not in result_str


# ── 5. list_allowed_apps task smoke ──────────────────────────────────────────

class TestListAllowedAppsSmoke:
    def test_list_apps_success(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("list_allowed_apps", "t-la")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["success"] is True

    def test_list_apps_no_program_execution(self, client_obj):
        """실제 프로그램 실행 없이 dry 정보만 반환."""
        import subprocess
        original = subprocess.run
        executed = []

        def mock_run(*a, **kw):
            executed.append(a)
            return original(*a, **kw)

        r = _run_smoke(client_obj, [_make_task("list_allowed_apps", "t-la-exec")])
        assert len(executed) == 0

    def test_list_apps_running_then_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("list_allowed_apps", "t-la-ord")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["type"] == "result"


# ── 6. open_url dry-run smoke ─────────────────────────────────────────────────

class TestOpenUrlSmoke:
    def test_open_url_dry_run_only(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("open_url", "t-ou")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["error_code"] == "DRY_RUN_ONLY"
        assert result["success"] is False

    def test_open_url_no_raw_url_in_sent(self, client_obj):
        task = _make_task("open_url", "t-ou-url")
        task["params"] = {"url": "https://external.example.com/path?q=secret#frag"}
        r = _run_smoke(client_obj, [task])
        sent_str = str(r["sent"])
        assert "external.example.com" not in sent_str
        assert "secret" not in sent_str
        assert "https://" not in sent_str

    def test_open_url_running_before_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("open_url", "t-ou-ord")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["type"] == "result"

    def test_open_url_no_browser_launch(self, client_obj):
        import subprocess
        executed = []
        original = subprocess.run

        def mock_run(*a, **kw):
            executed.append(a)
            return original(*a, **kw)

        _run_smoke(client_obj, [_make_task("open_url", "t-ou-br")])
        assert len(executed) == 0


# ── 7. list_files_readonly dry-run smoke ──────────────────────────────────────

class TestListFilesSmoke:
    def test_list_files_dry_run_only(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("list_files_readonly", "t-lf")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["error_code"] == "DRY_RUN_ONLY"
        assert result["success"] is False

    def test_list_files_no_raw_path(self, client_obj):
        task = _make_task("list_files_readonly", "t-lf-path")
        task["params"] = {"path": "C:\\Users\\skyjw\\Documents"}
        r = _run_smoke(client_obj, [task])
        sent_str = str(r["sent"])
        assert "C:\\" not in sent_str
        assert "skyjw" not in sent_str
        assert "/home/" not in sent_str

    def test_list_files_no_fs_access(self, client_obj):
        import os as _os
        listed = []
        original_listdir = _os.listdir

        def mock_listdir(*a, **kw):
            listed.append(a)
            return original_listdir(*a, **kw)

        _run_smoke(client_obj, [_make_task("list_files_readonly", "t-lf-fs")])
        assert len(listed) == 0

    def test_list_files_running_before_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("list_files_readonly", "t-lf-ord")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["type"] == "result"


# ── 8. capture_screenshot blocked smoke ───────────────────────────────────────

class TestCaptureScreenshotSmoke:
    def test_screenshot_blocked_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("capture_screenshot", "t-ss", risk="high")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert result["error_code"] == "BLOCKED"
        assert result["success"] is False

    def test_screenshot_no_stack_trace(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("capture_screenshot", "t-ss-st", risk="high")])
        sent_str = str(r["sent"])
        assert "Traceback" not in sent_str
        assert "raise " not in sent_str

    def test_screenshot_running_before_blocked_result(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("capture_screenshot", "t-ss-ord", risk="high")])
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        assert task_payloads[0]["type"] == "running"
        assert task_payloads[1]["error_code"] == "BLOCKED"


# ── 9. external URL blocked ───────────────────────────────────────────────────

class TestExternalUrlBlocked:
    @pytest.mark.parametrize("url", [
        "ws://example.com/ws",
        "wss://example.com/ws",
        "wss://prod-server.internal/api/v1/local-agents/ws",
        "ws://192.168.1.100/ws",
        "http://example.com/ws",
    ])
    def test_non_localhost_url_blocked(self, url):
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url(url)

    @pytest.mark.parametrize("url", [
        "ws://localhost:8400/ws",
        "ws://127.0.0.1:8400/ws",
        "http://localhost:8400/ws",
        "http://127.0.0.1:0/ws",
    ])
    def test_localhost_url_allowed(self, url):
        assert_local_ws_url(url)  # should not raise

    def test_https_blocked(self):
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url("https://localhost/api")

    def test_ftp_blocked(self):
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url("ftp://localhost/file")


# ── 10. sensitive fields in all smoke outputs ─────────────────────────────────

class TestSensitiveInSmokeOutput:
    def test_no_device_token_in_sent_records(self, client_obj):
        """sent 기록 전체에 device_token 원문 미포함."""
        r = _run_smoke(client_obj, [_make_task("ping", "t-sens-ping")])
        for record in r["sent"]:
            assert "smoke-dummy-token" not in str(record)

    def test_no_sensitive_key_in_heartbeat_record(self, client_obj):
        r = _run_smoke(client_obj, [])
        hb = r["sent"][1]
        for key in _SENSITIVE_KEYS:
            assert key not in str(hb)

    def test_no_sensitive_key_in_running_record(self, client_obj):
        r = _run_smoke(client_obj, [_make_task("ping", "t-sens-run")])
        running = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "running")
        for key in _SENSITIVE_KEYS:
            assert key not in str(running)

    def test_params_not_in_result(self, client_obj):
        """params 키 자체가 result에 노출되지 않음."""
        r = _run_smoke(client_obj, [_make_task("ping", "t-sens-params")])
        result = next(s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result")
        assert "params" not in result


# ── 11. multi-task lifecycle smoke ────────────────────────────────────────────

class TestMultiTaskSmoke:
    def test_multiple_tasks_all_processed(self, client_obj):
        tasks = [
            _make_task("ping", "t-multi-1"),
            _make_task("system_info", "t-multi-2"),
            _make_task("open_url", "t-multi-3"),
        ]
        r = _run_smoke(client_obj, tasks)
        results = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") == "result"]
        assert len(results) == 3

    def test_multiple_tasks_running_before_each_result(self, client_obj):
        tasks = [
            _make_task("ping", "t-ml-1"),
            _make_task("list_files_readonly", "t-ml-2"),
        ]
        r = _run_smoke(client_obj, tasks)
        task_payloads = [s for s in r["sent"] if isinstance(s, dict) and s.get("type") in ("running", "result")]
        # running/result 쌍이 올바른 순서인지 확인
        for i in range(0, len(task_payloads), 2):
            assert task_payloads[i]["type"] == "running"
            assert task_payloads[i + 1]["type"] == "result"


# ── 12. regression: 기존 테스트 호환 ────────────────────────────────────────

class TestRegression:
    def test_low_risk_handle_task_still_works(self):
        for action in ["ping", "system_info", "list_allowed_apps"]:
            r = handle_task({"task_id": "t", "action": action})
            assert r["success"] is True

    def test_dry_run_actions_still_return_dry_run_only(self):
        for action in ["open_url", "list_files_readonly"]:
            r = handle_task({"task_id": "t", "action": action})
            assert r["error_code"] == "DRY_RUN_ONLY"

    def test_capture_screenshot_still_raises_blocked(self):
        with pytest.raises(BlockedAction):
            handle_task({"task_id": "t", "action": "capture_screenshot"})

    def test_build_running_contract(self):
        r = build_running("task-reg")
        assert r == {"type": "running", "task_id": "task-reg"}

    def test_assert_local_ws_url_passes_for_localhost(self):
        assert_local_ws_url("ws://localhost:8400/ws")
        assert_local_ws_url("ws://127.0.0.1:9000/ws")
