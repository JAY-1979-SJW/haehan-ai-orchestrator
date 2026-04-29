"""Stage 13F-2F: local-only server router integration gate.

실제 ai_orchestrator local_agent_router WebSocket 엔드포인트를
FastAPI TestClient in-process로 구동하고,
agent/local_agent_client.py 의 빌딩 함수들이 실제 서버와 호환되는지 검증한다.

- 외부 네트워크 없음
- 운영 서버 연결 없음
- 실제 DB 없음
- device_token은 테스트 더미만 사용, 로그/result에 노출 없음
- 모든 WS 연결 대상은 in-process TestClient (localhost 제한 적용 아님)

서버 흐름(실제 router):
  1. auth → auth_ok
  2. auth_ok 직후 서버가 queued task를 즉시 push (auth + _push_queued)
  3. heartbeat → heartbeat_ack (+ 추가 queued task push)
  4. task: client → running → server running_ack
  5. task: client → result → server result_ack
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.local_agent_client import (
    BlockedAction,
    ExternalUrlBlocked,
    assert_local_ws_url,
    build_auth,
    build_heartbeat,
    build_result,
    build_running,
    handle_task,
    load_config,
    strip_sensitive,
)

# ── 민감 키 목록 ──────────────────────────────────────────────────────────────

_SENSITIVE_KEYS = {
    "device_token", "token", "password", "passwd", "pwd",
    "secret", "cookie", "authorization", "raw_params",
    "api_key", "session",
}

# ── fixture: isolated server ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """레지스트리·감사로그·승인토큰 격리 (각 테스트 독립)."""
    import importlib
    import ai_orchestrator.auth as _auth
    importlib.reload(_auth)
    import ai_orchestrator.local_agent_router as _lar
    importlib.reload(_lar)

    import ai_orchestrator.audit_logger as _al
    import ai_orchestrator.approval as _ap
    import ai_orchestrator.local_agent_registry as _reg

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "gate_admin", "role": "admin"}


def _make_server_client(user: dict) -> TestClient:
    from ai_orchestrator.local_agent_router import local_agent_router
    from ai_orchestrator.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def _register(tc: TestClient) -> tuple[str, str]:
    """테스트 에이전트 등록 → (agent_id, device_token) 반환. token은 출력 금지."""
    resp = tc.post("/api/v1/local-agents/register", json={
        "host": "gate-test-pc", "os_name": "Windows 11", "version": "0.1.0",
    }).json()
    return resp["agent_id"], resp["device_token"]


def _enqueue(tc: TestClient, agent_id: str, action: str, params: Optional[dict] = None) -> dict:
    return tc.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={"action": action, "params": params or {}},
    ).json()


def _get_task(tc: TestClient, agent_id: str, task_id: str) -> dict:
    return tc.get(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}").json()


def _no_sensitive_in(payload) -> None:
    """페이로드 문자열 표현에 민감 키가 없어야 한다 (auth payload 제외)."""
    s = str(payload)
    for key in _SENSITIVE_KEYS:
        assert key not in s, f"sensitive key {key!r} found in payload: {s[:200]}"


# ── 1. auth gate ──────────────────────────────────────────────────────────────

class TestAuthGate:
    def test_valid_token_auth_ok(self, admin_user):
        """유효한 device_token으로 auth_ok 수신."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            auth_payload = build_auth(agent_id, token)
            ws.send_json(auth_payload)
            resp = ws.receive_json()
            assert resp["type"] == "auth_ok"
            assert resp["agent_id"] == agent_id

    def test_invalid_token_rejected(self, admin_user):
        """잘못된 device_token → close(4401)."""
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)

        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
                ws.send_json(build_auth(agent_id, "bad-token-not-real"))
                ws.receive_json()
        assert exc.value.code == 4401

    def test_unknown_agent_id_rejected(self, admin_user):
        """미등록 agent_id → close(4401)."""
        tc = _make_server_client(admin_user)
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
                ws.send_json(build_auth("la-ghost-00000", "any-token"))
                ws.receive_json()
        assert exc.value.code == 4401

    def test_auth_payload_no_sensitive_in_response(self, admin_user):
        """auth_ok 응답에 device_token 미포함."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            resp = ws.receive_json()
            assert "device_token" not in resp
            assert "token" not in str(resp)

    def test_non_auth_first_message_rejected(self, admin_user):
        """첫 메시지가 auth 아닌 경우 close(4401)."""
        tc = _make_server_client(admin_user)
        _register(tc)
        with pytest.raises(WebSocketDisconnect) as exc:
            with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
                ws.send_json({"type": "heartbeat"})
                ws.receive_json()
        assert exc.value.code == 4401

    def test_build_auth_format_accepted_by_server(self, admin_user):
        """build_auth() 형식이 실제 서버에서 auth_ok를 받는지 확인."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        auth = build_auth(agent_id, token)
        assert auth["type"] == "auth"
        assert auth["agent_id"] == agent_id
        assert "device_token" in auth

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(auth)
            resp = ws.receive_json()
            assert resp["type"] == "auth_ok"


# ── 2. heartbeat gate ─────────────────────────────────────────────────────────

class TestHeartbeatGate:
    def _connect_auth(self, tc: TestClient, agent_id: str, token: str):
        """auth → auth_ok 완료 후 WS 객체 반환 (context manager 내에서 사용)."""
        raise NotImplementedError  # 인라인 사용

    def test_heartbeat_ack_received(self, admin_user):
        """build_heartbeat() 전송 시 서버가 heartbeat_ack 반환."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            resp = ws.receive_json()
            assert resp["type"] == "auth_ok"

            hb = build_heartbeat(agent_id)
            ws.send_json(hb)
            ack = ws.receive_json()
            assert ack["type"] == "heartbeat_ack"

    def test_heartbeat_no_token(self, admin_user):
        """heartbeat payload에 token/device_token 미포함."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            ws.receive_json()  # auth_ok

            hb = build_heartbeat(agent_id)
            for key in _SENSITIVE_KEYS:
                assert key not in hb, f"sensitive key {key!r} in heartbeat"
            ws.send_json(hb)
            ack = ws.receive_json()
            assert ack["type"] == "heartbeat_ack"

    def test_heartbeat_updates_agent_last_seen(self, admin_user):
        """heartbeat 후 agent last_seen_at 갱신 확인."""
        import ai_orchestrator.local_agent_registry as _reg
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            ws.receive_json()  # auth_ok

            ws.send_json(build_heartbeat(agent_id))
            ws.receive_json()  # heartbeat_ack

        agent = _reg.get_agent(agent_id)
        assert agent is not None
        assert agent.last_seen_at  # heartbeat로 갱신됨


# ── 3. ping task gate (서버 auto-complete) ────────────────────────────────────

class TestPingTaskGate:
    def test_ping_server_auto_complete(self, admin_user):
        """ping은 서버가 즉시 completed 처리 — WS로 전달되지 않음."""
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)

        task = _enqueue(tc, agent_id, "ping")
        assert task["status"] == "completed"

    def test_ping_client_result_format_server_compatible(self, admin_user):
        """ping에 대한 client result payload가 서버 result_ack와 호환되는지 확인.

        서버가 직접 완료하므로 WS로 result를 전송할 필요는 없지만,
        클라이언트가 생성하는 result 형식이 서버 스키마와 호환되는지 검증한다.
        """
        task_dict = {"task_id": "t-gate-ping", "action": "ping", "params": {}}
        result = handle_task(task_dict)
        assert result["type"] == "result"
        assert result["success"] is True
        assert result["task_id"] == "t-gate-ping"
        _no_sensitive_in(result)

    def test_ping_running_format(self):
        """build_running() 결과가 서버 running_ack 스키마와 호환."""
        running = build_running("t-gate-ping-run")
        assert running["type"] == "running"
        assert running["task_id"] == "t-gate-ping-run"
        _no_sensitive_in(running)


# ── 4. system_info task gate ──────────────────────────────────────────────────

class TestSystemInfoGate:
    def test_system_info_server_auto_complete(self, admin_user):
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)
        task = _enqueue(tc, agent_id, "system_info")
        assert task["status"] == "completed"

    def test_system_info_client_result_format(self):
        task_dict = {"task_id": "t-gate-si", "action": "system_info", "params": {}}
        result = handle_task(task_dict)
        assert result["success"] is True
        _no_sensitive_in(result)


# ── 5. list_allowed_apps gate ─────────────────────────────────────────────────

class TestListAllowedAppsGate:
    def test_list_apps_server_auto_complete(self, admin_user):
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)
        task = _enqueue(tc, agent_id, "list_allowed_apps")
        assert task["status"] == "completed"

    def test_list_apps_client_result_format(self):
        task_dict = {"task_id": "t-gate-la", "action": "list_allowed_apps", "params": {}}
        result = handle_task(task_dict)
        assert result["success"] is True
        _no_sensitive_in(result)
        assert "browser" in result.get("summary", "")


# ── 6. open_url WS gate ───────────────────────────────────────────────────────

class TestOpenUrlWsGate:
    def test_open_url_queued_on_enqueue(self, admin_user):
        """open_url은 서버에서 queued → WS로 전달."""
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)
        task = _enqueue(tc, agent_id, "open_url", {"url": "https://example.com"})
        assert task["status"] == "queued"

    def test_open_url_full_ws_lifecycle(self, admin_user):
        """open_url WS 전체 생명주기: delivered → running → failed(DRY_RUN_ONLY)."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        task_resp = _enqueue(tc, agent_id, "open_url", {"url": "https://example.com"})
        task_id = task_resp["task_id"]

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            # auth
            ws.send_json(build_auth(agent_id, token))
            assert ws.receive_json()["type"] == "auth_ok"

            # 서버가 auth_ok 직후 queued task 전송
            task_msg = ws.receive_json()
            assert task_msg["type"] == "task"
            assert task_msg["task"]["task_id"] == task_id
            assert task_msg["task"]["action"] == "open_url"
            assert "device_token" not in str(task_msg)

            # client: running 전송
            running = build_running(task_id)
            ws.send_json(running)
            running_ack = ws.receive_json()
            assert running_ack["type"] == "running_ack"
            assert running_ack["task_id"] == task_id

            # client: handle_task로 result 생성
            task_dict = task_msg["task"]
            result = handle_task(task_dict)
            assert result["error_code"] == "DRY_RUN_ONLY"
            assert result["success"] is False
            _no_sensitive_in(result)

            # result 전송
            ws.send_json(result)
            result_ack = ws.receive_json()
            assert result_ack["type"] == "result_ack"
            assert result_ack["task_id"] == task_id

        # 서버 task status 확인 — DRY_RUN_ONLY(success=False) → failed
        final = _get_task(tc, agent_id, task_id)
        assert final["status"] == "failed"
        assert "DRY_RUN_ONLY" in final.get("error_summary", "")

    def test_open_url_running_no_sensitive(self, admin_user):
        """running payload에 민감정보 없음."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        task_resp = _enqueue(tc, agent_id, "open_url")
        task_id = task_resp["task_id"]

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            ws.receive_json()  # auth_ok
            ws.receive_json()  # task

            running = build_running(task_id)
            for key in _SENSITIVE_KEYS:
                assert key not in running
            ws.send_json(running)
            ws.receive_json()  # running_ack

    def test_open_url_result_no_raw_url(self, admin_user):
        """result payload에 raw URL/query/fragment 미포함."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        _enqueue(tc, agent_id, "open_url", {"url": "https://sensitive.example.com?q=leak#frag"})

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            ws.receive_json()
            task_msg = ws.receive_json()

            task_dict = task_msg["task"]
            result = handle_task(task_dict)
            result_str = str(result)
            assert "sensitive.example.com" not in result_str
            assert "?q=leak" not in result_str
            assert "#frag" not in result_str


# ── 7. list_files_readonly WS gate ───────────────────────────────────────────

class TestListFilesWsGate:
    def test_list_files_full_ws_lifecycle(self, admin_user):
        """list_files_readonly WS 전체 생명주기."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        task_resp = _enqueue(tc, agent_id, "list_files_readonly", {"path": "/some/dir"})
        task_id = task_resp["task_id"]

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            assert ws.receive_json()["type"] == "auth_ok"

            task_msg = ws.receive_json()
            assert task_msg["type"] == "task"
            assert task_msg["task"]["action"] == "list_files_readonly"
            # 서버가 민감 params를 strip하므로 path가 있을 수 있지만
            # client result에는 raw path 미포함 확인
            assert "device_token" not in str(task_msg)

            # running
            running = build_running(task_id)
            ws.send_json(running)
            running_ack = ws.receive_json()
            assert running_ack["type"] == "running_ack"

            # result (DRY_RUN_ONLY)
            task_dict = task_msg["task"]
            result = handle_task(task_dict)
            assert result["error_code"] == "DRY_RUN_ONLY"
            result_str = str(result)
            assert "/some/dir" not in result_str
            assert "C:\\" not in result_str

            ws.send_json(result)
            result_ack = ws.receive_json()
            assert result_ack["type"] == "result_ack"

        final = _get_task(tc, agent_id, task_id)
        assert final["status"] == "failed"

    def test_list_files_result_no_raw_path(self, admin_user):
        """result에 raw path/absolute path 미포함."""
        task_dict = {
            "task_id": "t-lf-gate",
            "action": "list_files_readonly",
            "params": {"path": "C:\\Users\\skyjw\\Documents"},
        }
        result = handle_task(task_dict)
        result_str = str(result)
        assert "C:\\" not in result_str
        assert "skyjw" not in result_str
        assert "Documents" not in result_str
        assert result["error_code"] == "DRY_RUN_ONLY"


# ── 8. capture_screenshot blocked gate ───────────────────────────────────────

class TestCaptureScreenshotGate:
    def test_capture_screenshot_waiting_approval(self, admin_user):
        """capture_screenshot은 서버에서 waiting_approval — WS로 전달 안 됨."""
        tc = _make_server_client(admin_user)
        agent_id, _ = _register(tc)
        task = _enqueue(tc, agent_id, "capture_screenshot")
        assert task["status"] == "waiting_approval"

    def test_capture_screenshot_not_delivered_via_ws(self, admin_user):
        """capture_screenshot은 승인 전 WS로 push되지 않음."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        _enqueue(tc, agent_id, "capture_screenshot")

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            assert ws.receive_json()["type"] == "auth_ok"
            # 서버가 push한 task가 없으면 heartbeat_ack 이전에 task 없음
            ws.send_json(build_heartbeat(agent_id))
            ack = ws.receive_json()
            assert ack["type"] == "heartbeat_ack"
            # 여기서 받은 메시지가 task이면 capture_screenshot이 잘못 push된 것
            # (heartbeat_ack만 받아야 함)

    def test_capture_screenshot_client_blocked(self):
        """handle_task는 capture_screenshot에 BlockedAction 발생."""
        with pytest.raises(BlockedAction):
            handle_task({"task_id": "t", "action": "capture_screenshot"})

    def test_capture_screenshot_result_no_stack_trace(self):
        """blocked result에 stack trace 미포함."""
        try:
            handle_task({"task_id": "t-ss-gate", "action": "capture_screenshot"})
        except BlockedAction:
            pass
        # build_result로 BLOCKED result 생성 후 확인
        blocked_result = build_result(
            task_id="t-ss-gate",
            success=False,
            error_code="BLOCKED",
            error="action is high-risk and blocked",
        )
        result_str = str(blocked_result)
        assert "Traceback" not in result_str
        assert "raise " not in result_str
        _no_sensitive_in(blocked_result)


# ── 9. sensitive output gate ──────────────────────────────────────────────────

class TestSensitiveOutputGate:
    def test_build_running_no_sensitive(self):
        running = build_running("t-gate-sens")
        for key in _SENSITIVE_KEYS:
            assert key not in running

    def test_build_heartbeat_no_sensitive(self):
        hb = build_heartbeat("gate-agent")
        for key in _SENSITIVE_KEYS:
            assert key not in hb

    def test_build_result_observe_summary_stripped(self):
        obs = {"token": "leak", "url_category": "safe", "count": 1}
        r = build_result("t", success=True, observe_summary=obs)
        assert "token" not in r["observe_summary"]
        assert r["observe_summary"]["url_category"] == "safe"

    def test_build_result_audit_summary_stripped(self):
        audit = {"secret": "leak", "event_count": 3}
        r = build_result("t", success=True, audit_summary=audit)
        assert "secret" not in r["audit_summary"]

    def test_strip_sensitive_all_keys(self):
        for key in _SENSITIVE_KEYS:
            result = strip_sensitive({key: "SHOULD_BE_GONE", "safe": "ok"})
            assert key not in result, f"key {key!r} not stripped"
            assert result["safe"] == "ok"

    def test_auth_ok_response_no_device_token(self, admin_user):
        """서버 auth_ok 응답에 device_token 노출 없음."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            resp = ws.receive_json()
            assert "device_token" not in resp
            assert token not in str(resp)

    def test_result_ack_no_sensitive(self, admin_user):
        """result_ack에 민감정보 없음."""
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        task_resp = _enqueue(tc, agent_id, "open_url")
        task_id = task_resp["task_id"]

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            ws.receive_json()
            ws.receive_json()  # task

            ws.send_json(build_running(task_id))
            ws.receive_json()  # running_ack

            result = build_result(task_id, success=False, error_code="DRY_RUN_ONLY")
            ws.send_json(result)
            ack = ws.receive_json()
            _no_sensitive_in(ack)


# ── 10. external block regression ────────────────────────────────────────────

class TestExternalBlockRegression:
    @pytest.mark.parametrize("url", [
        "ws://example.com/ws",
        "wss://example.com/ws",
        "wss://prod-server.internal/ws",
        "ws://192.168.1.100:8400/ws",
        "https://example.com/api",
    ])
    def test_non_localhost_blocked(self, url):
        with pytest.raises(ExternalUrlBlocked):
            assert_local_ws_url(url)

    @pytest.mark.parametrize("url", [
        "ws://localhost:8400/ws",
        "ws://127.0.0.1:8400/ws",
        "http://localhost:8400/ws",
    ])
    def test_localhost_allowed(self, url):
        assert_local_ws_url(url)  # should not raise


# ── 11. multi-task WS gate ────────────────────────────────────────────────────

class TestMultiTaskWsGate:
    def test_two_tasks_sequential(self, admin_user):
        """open_url + list_files_readonly 두 task가 순서대로 처리됨.

        서버는 auth_ok 직후 _push_queued로 모든 queued task를 한꺼번에 push한다.
        따라서 task 수신 → 순서대로 처리 흐름을 따라야 한다.
        """
        tc = _make_server_client(admin_user)
        agent_id, token = _register(tc)
        t1 = _enqueue(tc, agent_id, "open_url")
        t2 = _enqueue(tc, agent_id, "list_files_readonly")

        with tc.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json(build_auth(agent_id, token))
            assert ws.receive_json()["type"] == "auth_ok"

            # 서버가 auth_ok 직후 두 task를 한꺼번에 push
            task1_msg = ws.receive_json()
            task2_msg = ws.receive_json()
            assert task1_msg["type"] == "task"
            assert task2_msg["type"] == "task"
            tasks = [task1_msg["task"], task2_msg["task"]]

            # 두 task를 순서대로 처리
            for task_dict in tasks:
                task_id = task_dict["task_id"]

                ws.send_json(build_running(task_id))
                running_ack = ws.receive_json()
                assert running_ack["type"] == "running_ack"
                assert running_ack["task_id"] == task_id

                result = handle_task(task_dict)
                assert result["error_code"] == "DRY_RUN_ONLY"
                _no_sensitive_in(result)

                ws.send_json(result)
                result_ack = ws.receive_json()
                assert result_ack["type"] == "result_ack"
                assert result_ack["task_id"] == task_id

        # 두 task 모두 failed 확인
        f1 = _get_task(tc, agent_id, t1["task_id"])
        f2 = _get_task(tc, agent_id, t2["task_id"])
        assert f1["status"] == "failed"
        assert f2["status"] == "failed"


# ── 12. production URL guard ──────────────────────────────────────────────────

class TestProductionUrlGuard:
    def test_env_production_url_would_be_blocked(self):
        """환경변수에 운영 URL이 있어도 assert_local_ws_url이 차단함을 검증."""
        import os
        prod_urls = [
            os.environ.get("LA_SERVER_URL", ""),
            os.environ.get("LA_WS_URL", ""),
        ]
        for url in prod_urls:
            if not url:
                continue
            url = url.strip()
            if not url:
                continue
            # 운영 URL이 환경변수에 있으면 반드시 차단되어야 한다
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""
            if host not in ("localhost", "127.0.0.1"):
                with pytest.raises(ExternalUrlBlocked):
                    assert_local_ws_url(url)

    def test_ws_url_contains_no_prod_domain(self):
        """로컬 agent config의 ws_url이 운영 도메인이 아님을 확인."""
        cfg = load_config(
            server_base_url="http://localhost:8400",
            agent_id="gate-test",
            device_token="dummy",
        )
        from agent.local_agent_client import LocalAgentClient
        client = LocalAgentClient(cfg)
        ws_url = client.ws_url
        import urllib.parse
        host = urllib.parse.urlparse(ws_url).hostname or ""
        # gate 테스트 설정이므로 반드시 localhost
        assert host == "localhost"
        assert_local_ws_url(ws_url)  # should not raise
