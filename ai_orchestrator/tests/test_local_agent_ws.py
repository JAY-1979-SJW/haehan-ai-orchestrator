"""로컬 에이전트 Stage 2 WebSocket 엔드포인트 검증.

필수 테스트:
  1. device_token 유효 시 WebSocket 연결 성공 (auth_ok)
  2. 잘못된 token 은 연결 거절 (close code=4401)
  3. agent_id 불일치 연결 거절
  4. queued task 가 에이전트로 전달 (delivered → task message)
  5. 에이전트 결과 수신 후 status=completed, timestamps 세팅
  6. 실패 보고 시 status=failed + error_summary
  7. open_url process_task 가 http/https 만 허용 (client 측 검증)
  8. forbidden action 은 process_task 단계에서 ACTION_FORBIDDEN
  9. high risk 작업은 waiting_approval 로 남고 WS 로 전달되지 않음
 10. device_token / 승인 token 원문이 감사 로그에 노출되지 않음
"""

from __future__ import annotations

import sys
from datetime import UTC
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    # auth/local_agent_router 를 reload 하지 않는다: reload 하면 get_current_user 가 시험마다 새 객체가 되는데
    # 하위 라우터는 처음 import 된 옛 객체에 묶여 있어 dependency_overrides 가 두 번째 시험부터 안 먹혀
    # 파일 전체 실행 시 등록이 401 이 되고 KeyError: 'agent_id' 가 난다(단독 실행만 통과, 2026-10-04 확인).
    import ai_orchestrator.agent_hub.registry.common as _reg_common
    import ai_orchestrator.agent_hub.registry.facade as _reg
    import ai_orchestrator.audit.audit_logger as _al
    import tools.gates.approval as _ap

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")
    # 2026-09-29 영속화 추가 후 필수: 안 하면 _reg.clear()가 실제 개발 세션의
    # data/local_agent_registry_state.json(실제 등록된 로컬 에이전트 상태)을 테스트마다 지운다.
    monkeypatch.setattr(_reg_common, "_REGISTRY_STATE_PATH", tmp_path / "local_agent_registry_state.json")

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _register(client) -> tuple[str, str]:
    reg = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "ws-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
    return reg["agent_id"], reg["device_token"]


def _enqueue(client, agent_id: str, action: str, params: dict | None = None) -> dict:
    return client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={"action": action, "params": params or {}},
    ).json()


# ── 1. auth 성공 ────────────────────────────────────────────────────────


def test_ws_auth_success(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json(
            {
                "type": "auth",
                "agent_id": agent_id,
                "device_token": token,
            }
        )
        first = ws.receive_json()
        assert first["type"] == "auth_ok"
        assert first["agent_id"] == agent_id


# ── 2. auth 실패: 잘못된 token ─────────────────────────────────────────


def test_ws_auth_bad_token(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)

    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json(
            {
                "type": "auth",
                "agent_id": agent_id,
                "device_token": "not_the_real_token_at_all",
            }
        )
        ws.receive_json()  # 서버가 즉시 close
    assert exc_info.value.code == 4401


# ── 3. auth 실패: agent_id 불일치 ──────────────────────────────────────


def test_ws_auth_unknown_agent_id(admin_user):
    client = _make_test_client(admin_user)
    # 등록된 에이전트 없이 임의 agent_id 로 접속 시도
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json(
            {
                "type": "auth",
                "agent_id": "la-ghost000000",
                "device_token": "any",
            }
        )
        ws.receive_json()
    assert exc_info.value.code == 4401


def test_ws_auth_agent_id_mismatch(admin_user):
    """agent A 의 토큰으로 agent B 를 가장할 수 없다."""
    client = _make_test_client(admin_user)
    agent_a, token_a = _register(client)
    agent_b, _ = _register(client)
    assert agent_a != agent_b

    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json(
            {
                "type": "auth",
                "agent_id": agent_b,  # 다른 agent 의 id
                "device_token": token_a,  # A 의 토큰
            }
        )
        ws.receive_json()
    assert exc_info.value.code == 4401


def test_ws_first_message_must_be_auth(admin_user):
    client = _make_test_client(admin_user)
    _register(client)

    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/api/v1/local-agents/ws") as ws:
        # auth 가 아닌 heartbeat 로 시작
        ws.send_json({"type": "heartbeat"})
        ws.receive_json()
    assert exc_info.value.code == 4401


# ── 4. queued task 전달 ─────────────────────────────────────────────────


def test_ws_initial_queued_task_pushed_on_auth(admin_user):
    """auth 직후 미리 queued 상태인 작업이 모두 push 되어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    # 먼저 open_url task 등록 → status=queued
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/a"})
    assert created["status"] == "queued"
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == task_id
        assert msg["task"]["action"] == "open_url"
        assert msg["task"]["params"]["url"] == "https://example.com/a"
        # 민감 필드는 dispatch 에 포함되지 않는다
        assert "requested_by" not in msg["task"]

        # HTTP 조회는 연결 유지 중에 수행 — disconnect 처리 전이므로 delivered 상태
        fetched = client.get(
            f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
        ).json()
        assert fetched["status"] == "delivered"
        assert fetched["delivered_at"]


def test_ws_pull_delivers_newly_enqueued(admin_user):
    """연결 중 enqueue 된 task 도 pull 메시지로 수령 가능."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

        created = _enqueue(client, agent_id, "open_url", {"url": "https://example.org/b"})
        task_id = created["task_id"]

        ws.send_json({"type": "pull"})
        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == task_id


# ── 5. result 수신 후 completed ────────────────────────────────────────


def test_ws_result_marks_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/ok"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        ws.send_json(
            {
                "type": "running",
                "task_id": task_id,
            }
        )
        assert ws.receive_json()["type"] == "running_ack"

        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": "opened: https://example.com/ok",
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"
        assert ack["status"] == "completed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "completed"
    assert fetched["started_at"]
    assert fetched["completed_at"]
    assert fetched["result_summary"].startswith("opened:")


# ── 6. 실패 보고 → failed + error_summary ──────────────────────────────


def test_ws_result_failure_marks_failed(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/x"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": False,
                "summary": "browser open failed",
                "error": "webbrowser module error",
                "error_code": "BROWSER_OPEN_FAILED",
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"
        assert ack["status"] == "failed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "failed"
    assert "BROWSER_OPEN_FAILED" in fetched["error_summary"]


# ── 7. open_url 은 http/https 만 (client process_task) ─────────────────


def test_client_process_task_open_url_scheme_guard(monkeypatch):
    """open_url dry-run 기본 동작과 스킴 가드 검증.

    open_url 은 기본적으로 dry_run=true 로 동작하며, 이 경우 실제 브라우저를 열지 않는다.
    스킴 가드(file/javascript/data)는 dry_run 여부와 무관하게 URL 검증 단계에서 차단된다.
    """
    import webbrowser

    opened: list[str] = []

    def fake_open(url, new=0, autoraise=True):
        opened.append(url)
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)

    from core.agent_runtime.connection.websocket_client import process_task

    # 기본값: dry_run=true (명시적으로 지정하지 않음)
    result = process_task(
        {
            "task_id": "t-1",
            "action": "open_url",
            "risk_level": "low",
            "params": {"url": "https://example.com/a"},
        }
    )
    assert result["type"] == "result"
    assert result["task_id"] == "t-1"
    assert result["success"] is True
    # dry_run=true 기본값이므로 webbrowser.open 호출 안 됨
    assert opened == []

    # 스킴 가드: 위험한 스킴은 dry_run 여부와 무관하게 차단
    for bad_url in ("file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "data:text/html,<script>x</script>"):
        r = process_task(
            {
                "task_id": "t-bad",
                "action": "open_url",
                "risk_level": "low",
                "params": {"url": bad_url},
            }
        )
        assert r["success"] is False
        assert r["error_code"] in {"URL_SCHEME_NOT_ALLOWED", "INVALID_URL"}

    # 여전히 webbrowser.open 호출 없음
    assert opened == []


# ── 8. forbidden action 은 본 클라이언트에서 실행 불가 ──────────────────


@pytest.mark.parametrize(
    "action",
    [
        "delete_file",
        "upload_file",
        "modify_file",
        "execute_shell",
    ],
)
def test_client_process_task_forbidden_action(action):
    from core.agent_runtime.connection.websocket_client import process_task

    r = process_task(
        {
            "task_id": "t-forbid",
            "action": action,
            "risk_level": "low",
            "params": {},
        }
    )
    assert r["success"] is False
    assert r["error_code"] == "ACTION_FORBIDDEN"


def test_client_process_task_unknown_auto_exec_action():
    from core.agent_runtime.connection.websocket_client import process_task

    r = process_task(
        {
            "task_id": "t-unk",
            "action": "mystery",
            "risk_level": "low",
            "params": {},
        }
    )
    assert r["success"] is False
    assert r["error_code"] in {
        "ACTION_NOT_AUTO_EXECUTABLE",
        "UNKNOWN_ACTION",
    }


# ── 9. high risk 는 WS 전달 금지 + 클라이언트도 거절 ───────────────────


def test_ws_high_risk_task_not_delivered(admin_user):
    """waiting_approval 상태의 high risk 작업은 WS 로 전달되지 않는다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "capture_screenshot")
    assert created["status"] == "waiting_approval"
    assert created["token_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

        # pull 후에도 task 가 없어야 한다 (heartbeat_ack 만)
        ws.send_json({"type": "heartbeat"})
        msg = ws.receive_json()
        assert msg["type"] == "heartbeat_ack"
        # 추가 push 시도 — 아무 task 도 오지 않아야 한다
        ws.send_json({"type": "pull"})
        # pull 은 별도 ack 가 없으므로 다음 heartbeat 로 확인
        ws.send_json({"type": "heartbeat"})
        next_msg = ws.receive_json()
        assert next_msg["type"] == "heartbeat_ack"

    # 상태는 그대로 waiting_approval
    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{created['task_id']}",
    ).json()
    assert fetched["status"] == "waiting_approval"


def test_client_process_task_high_risk_returns_not_implemented_stage2():
    from core.agent_runtime.connection.websocket_client import process_task

    r = process_task(
        {
            "task_id": "t-hr",
            "action": "capture_screenshot",
            "risk_level": "high",
            "params": {},
        }
    )
    assert r["success"] is False
    assert r["error_code"] == "NOT_IMPLEMENTED_STAGE2"


# ── 10. 감사 로그에 토큰 원문 / 민감값 노출 금지 ───────────────────────


def test_ws_device_token_never_in_audit_log(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    # 유효 / 무효 시도 모두
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        ws.receive_json()

    try:
        with client.websocket_connect("/api/v1/local-agents/ws") as ws2:
            ws2.send_json({"type": "auth", "agent_id": agent_id, "device_token": "raw_guess_value_zzz"})
            ws2.receive_json()
    except WebSocketDisconnect:
        pass

    raw = _al._LOG_PATH.read_text(encoding="utf-8")
    assert token not in raw, "device_token 원문이 감사 로그에 노출됨"
    assert "raw_guess_value_zzz" not in raw, "무효 token 시도 원문이 기록됨"


def test_ws_connected_and_disconnected_audit_events(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        ws.receive_json()

    events = {e["event_type"] for e in _al.read_recent_logs(limit=100)}
    assert "LOCAL_AGENT_WS_CONNECTED" in events
    assert "LOCAL_AGENT_WS_DISCONNECTED" in events


def test_ws_auth_failure_audit_event(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)

    try:
        with client.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": "wrong"})
            ws.receive_json()
    except WebSocketDisconnect:
        pass

    events = {e["event_type"] for e in _al.read_recent_logs(limit=100)}
    assert "LOCAL_AGENT_WS_AUTH_FAILED" in events


# ── sanity: auto-execute 매핑 일관성 ───────────────────────────────────


def test_server_and_client_auto_exec_sets_match():
    """서버와 클라이언트의 AUTO_EXECUTE_VIA_AGENT 집합은 동일해야 한다."""
    from ai_orchestrator.agent_hub.registry.facade import AUTO_EXECUTE_VIA_AGENT as _S
    from core.agent_runtime.connection.websocket_client import _AUTO_EXECUTE_VIA_AGENT as _C

    assert set(_S) == set(_C)


# ── agent 모니터링 필드 ───────────────────────────────────────────────────


def test_agent_registered_at_set_on_registration():
    """agent 등록 시 registered_at이 설정되어야 한다."""
    from ai_orchestrator.agent_hub.registry.facade import list_agents, register_agent

    list_agents()
    result = register_agent(host="mon-test", os_name="Windows", version="0.1", requested_by="test")
    agent = result.agent
    assert agent.registered_at
    assert "2026-04" in agent.registered_at or "T" in agent.registered_at


def test_agent_monitoring_fields_in_list_response(admin_user):
    """agent 목록 응답에 monitoring 필드가 포함되어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent is not None

    # 등록 직후 필드
    assert "registered_at" in agent
    assert agent["registered_at"]
    assert "agent_status" in agent
    assert agent["agent_status"] in ["offline", "online", "idle", "busy", "stale"]
    assert "connected_at" in agent
    assert "last_seen_at" in agent
    assert "disconnected_at" in agent
    assert "active_task_count" in agent
    assert agent["active_task_count"] == 0
    assert "current_task_id" in agent
    assert agent["current_task_id"] in ("", None) or isinstance(agent["current_task_id"], str)


def test_agent_status_online_after_ws_auth(admin_user):
    """WS auth 후 agent status가 online 또는 idle이어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

        agents = client.get("/api/v1/local-agents").json()["agents"]
        agent = next((a for a in agents if a["agent_id"] == agent_id), None)
        assert agent["agent_status"] in ["online", "idle"]
        assert agent["connected_at"]
        assert agent["last_seen_at"]


def test_agent_active_task_count_during_ws_delivery(admin_user):
    """task delivery 중 active_task_count가 1이어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "ws_noop")
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        agents = client.get("/api/v1/local-agents").json()["agents"]
        agent = next((a for a in agents if a["agent_id"] == agent_id), None)
        # delivered 상태에서 active_task_count는 1
        assert agent["active_task_count"] == 1
        assert agent["current_task_id"] in ("", None) or agent["current_task_id"] == task_id


def test_agent_current_task_id_during_running(admin_user):
    """running 상태에서 current_task_id가 task_id여야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "ws_noop")
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        ws.send_json({"type": "running", "agent_id": agent_id, "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        agents = client.get("/api/v1/local-agents").json()["agents"]
        agent = next((a for a in agents if a["agent_id"] == agent_id), None)
        assert agent["current_task_id"] == task_id
        assert agent["active_task_count"] == 1


def test_agent_active_task_count_zero_after_completion(admin_user):
    """task 완료 후 active_task_count가 0이어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "ws_noop")
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        ws.send_json({"type": "running", "agent_id": agent_id, "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        ws.send_json(
            {"type": "result", "agent_id": agent_id, "task_id": task_id, "success": True, "summary": "ws_noop_ok"}
        )
        assert ws.receive_json()["type"] == "result_ack"

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent["active_task_count"] == 0
    assert agent["current_task_id"] in ("", None)


def test_agent_status_offline_after_disconnect(admin_user):
    """WS disconnect 후 agent status가 offline이어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent["agent_status"] == "offline"
    assert agent["disconnected_at"]


def test_agent_device_token_not_in_response(admin_user):
    """agent 응답에 device_token이나 token_hash가 없어야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent is not None
    assert "device_token" not in agent
    assert "token_hash" not in agent
    assert token not in str(agent)


def test_agent_task_counts_accurate(admin_user):
    """agent task count 필드들이 정확해야 한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    # 초기: 모든 count 0
    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent["task_count"] == 0
    assert agent["completed_task_count"] == 0
    assert agent["failed_task_count"] == 0

    # 1개 task 생성
    created = _enqueue(client, agent_id, "ws_noop")
    task_id = created["task_id"]

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent["task_count"] == 1
    assert agent["completed_task_count"] == 0
    assert agent["failed_task_count"] == 0

    # task 완료
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "agent_id": agent_id, "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        ws.send_json(
            {"type": "result", "agent_id": agent_id, "task_id": task_id, "success": True, "summary": "ws_noop_ok"}
        )
        assert ws.receive_json()["type"] == "result_ack"

    agents = client.get("/api/v1/local-agents").json()["agents"]
    agent = next((a for a in agents if a["agent_id"] == agent_id), None)
    assert agent["task_count"] == 1
    assert agent["completed_task_count"] == 1
    assert agent["failed_task_count"] == 0


# ── 11. expire_stale_tasks — registry 단위 (now 주입) ───────────────────


def test_delivered_timeout_via_registry(admin_user):
    """delivered 상태 task가 DELIVERED_TIMEOUT_SECONDS 초과 시 failed로 전환된다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/to"})
    task_id = created["task_id"]

    # WS 연결 유지 중에 expire 호출 — disconnect 처리 전이므로 still delivered
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        task = _reg.find_task_by_id(task_id)
        assert task.status == "delivered"

        future = datetime.now(UTC) + timedelta(seconds=_reg.DELIVERED_TIMEOUT_SECONDS + 1)
        expired = _reg.expire_stale_tasks(now=future)

    assert len(expired) == 1
    assert expired[0].task_id == task_id
    assert expired[0].status == "failed"


def test_delivered_timeout_failure_reason(admin_user):
    """delivered timeout 후 failure_reason = delivered_timeout."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    _enqueue(client, agent_id, "open_url", {"url": "https://example.com/fr"})

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        future = datetime.now(UTC) + timedelta(seconds=_reg.DELIVERED_TIMEOUT_SECONDS + 1)
        expired = _reg.expire_stale_tasks(now=future)

    assert expired[0].failure_reason == "delivered_timeout"
    assert expired[0].timed_out_at != ""


def test_running_timeout_via_registry(admin_user):
    """running 상태 task가 RUNNING_TIMEOUT_SECONDS 초과 시 failed로 전환된다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/rt"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        task = _reg.find_task_by_id(task_id)
        assert task.status == "running"

        future = datetime.now(UTC) + timedelta(seconds=_reg.RUNNING_TIMEOUT_SECONDS + 1)
        expired = _reg.expire_stale_tasks(now=future)

    assert len(expired) == 1
    assert expired[0].task_id == task_id
    assert expired[0].status == "failed"


def test_running_timeout_failure_reason(admin_user):
    """running timeout 후 failure_reason = running_timeout."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/rfr"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        future = datetime.now(UTC) + timedelta(seconds=_reg.RUNNING_TIMEOUT_SECONDS + 1)
        expired = _reg.expire_stale_tasks(now=future)

    assert expired[0].failure_reason == "running_timeout"
    assert expired[0].timed_out_at != ""


def test_completed_failed_not_expired(admin_user):
    """completed / failed task는 expire_stale_tasks로 변경되지 않는다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    c1 = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/c1"})
    c2 = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/c2"})

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        # 단일 WS 세션은 한 번에 하나씩 delivered로 전환한다.
        assert ws.receive_json()["type"] == "task"

        ws.send_json({"type": "running", "task_id": c1["task_id"]})
        assert ws.receive_json()["type"] == "running_ack"

        # c1 완료
        ws.send_json(
            {
                "type": "result",
                "task_id": c1["task_id"],
                "success": True,
                "summary": "done",
            }
        )
        assert ws.receive_json()["type"] == "result_ack"

        # c2 실패
        assert ws.receive_json()["type"] == "task"
        ws.send_json(
            {
                "type": "result",
                "task_id": c2["task_id"],
                "success": False,
                "error_code": "ERR",
                "error": "fail",
            }
        )
        assert ws.receive_json()["type"] == "result_ack"

    assert _reg.find_task_by_id(c1["task_id"]).status == "completed"
    assert _reg.find_task_by_id(c2["task_id"]).status == "failed"

    far_future = datetime.now(UTC) + timedelta(hours=24)
    expired = _reg.expire_stale_tasks(now=far_future)
    assert len(expired) == 0


def test_ws_idle_timeout_triggers_expire_and_audit(admin_user, monkeypatch):
    """WS idle 처리 시 expire_stale_tasks가 호출되고 timeout audit이 기록된다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as _reg

    # 수신 timeout 상수는 WS 엔드포인트를 분리한 local_agent_router_ws 모듈이 소유한다(결함 #111)
    import ai_orchestrator.agent_hub.router.ws as _lar
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/audit"})
    task_id = created["task_id"]

    # WS idle을 즉시 트리거하기 위해 timeout을 최소화
    monkeypatch.setattr(_lar, "_WS_RECV_TIMEOUT_SEC", 0.01)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"  # delivered 전환

        # task delivered_at을 timeout 초과 과거로 조작
        task = _reg.find_task_by_id(task_id)
        task.delivered_at = (datetime.now(UTC) - timedelta(seconds=_reg.DELIVERED_TIMEOUT_SECONDS + 10)).isoformat()

        # 아무 메시지도 보내지 않으면 서버가 timeout → idle 처리
        msg = ws.receive_json()
        assert msg["type"] == "idle"

    events = [e["event_type"] for e in _al.read_recent_logs(limit=200)]
    assert "LOCAL_AGENT_TASK_TIMEOUT" in events

    task = _reg.find_task_by_id(task_id)
    assert task.status == "failed"
    assert task.failure_reason == "delivered_timeout"


# ── 12. disconnect 처리 — delivered/running → 재큐잉(재시도 소진 시 failed) ──
# 2026-09-30: 기존엔 delivered/running 중 disconnect되면 무조건 즉시 failed였다.
# 실사용 중 "에이전트 재기동 도중 몇 초 사이 들어온 요청이 그 자리에서 실패 처리"되는
# 증상이 실제로 재현돼(docs/defect_index.json), MAX_WS_DISCONNECT_RETRIES 만큼은
# queued로 되돌려 재연결 시 자동 재전달하도록 바뀌었다 — 아래 테스트도 이에 맞춰 갱신.


def test_delivered_task_requeued_on_first_disconnect(admin_user):
    """delivered 상태 task는 첫 WS disconnect 후 재큐잉(queued, retry_count=1)된다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d1"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        # disconnect — delivered 상태로 종료

    task = _reg.find_task_by_id(task_id)
    assert task.status == "queued"
    assert task.retry_count == 1
    assert task.delivered_at == ""


def test_running_task_failed_on_disconnect_not_requeued(admin_user):
    """running 상태 task는 이미 실행됐을 수 있어 disconnect 시 재큐잉 없이 failed 된다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d2"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        # disconnect — running 상태로 종료

    task = _reg.find_task_by_id(task_id)
    assert task.status == "failed"
    assert task.failure_reason == "websocket_disconnected"
    assert task.retry_count == 0


def test_requeued_task_redelivered_on_reconnect(admin_user):
    """재큐잉된 task는 같은 agent가 재연결하면 자동으로 다시 delivered 된다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d5"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
    assert _reg.find_task_by_id(task_id).status == "queued"

    # 같은 agent_id/token으로 재연결 — 재큐잉된 task가 자동으로 다시 push돼야 한다.
    with client.websocket_connect("/api/v1/local-agents/ws") as ws2:
        ws2.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws2.receive_json()["type"] == "auth_ok"
        pushed = ws2.receive_json()
        assert pushed["type"] == "task"
        assert pushed["task"]["task_id"] == task_id

    task = _reg.find_task_by_id(task_id)
    assert task.status == "queued"  # 두 번째 disconnect도 재큐잉(retry_count=2, 상한 미도달)
    assert task.retry_count == 2


def test_disconnect_fails_after_retries_exhausted(admin_user):
    """MAX_WS_DISCONNECT_RETRIES 만큼 재큐잉 후 또 disconnect되면 최종 failed가 된다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg
    from ai_orchestrator.agent_hub.registry.common import MAX_WS_DISCONNECT_RETRIES

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d6"})
    task_id = created["task_id"]

    # MAX_WS_DISCONNECT_RETRIES + 1 번 연속으로 delivered → disconnect 반복
    for _ in range(MAX_WS_DISCONNECT_RETRIES + 1):
        with client.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
            assert ws.receive_json()["type"] == "auth_ok"
            assert ws.receive_json()["type"] == "task"

    task = _reg.find_task_by_id(task_id)
    assert task.status == "failed"
    assert task.failure_reason == "websocket_disconnected"
    assert task.timed_out_at == ""  # timeout 아님
    assert task.retry_count == MAX_WS_DISCONNECT_RETRIES


def test_queued_task_unchanged_on_disconnect(admin_user):
    """queued 상태 task는 disconnect 후 그대로 queued이다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    # agent A로 auth 후 disconnect → queued task가 남아야 함
    # 두 번째 WS 세션 없이 진행: 직접 registry 함수 호출
    agent_id, _token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d4"})
    task_id = created["task_id"]
    assert created["status"] == "queued"

    # auth 없이 disconnect 처리만 직접 호출
    _reg.fail_active_tasks_for_agent(agent_id)

    task = _reg.find_task_by_id(task_id)
    assert task.status == "queued"


def test_completed_task_unchanged_on_disconnect(admin_user):
    """completed 상태 task는 disconnect 후 그대로 completed이다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d5"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": "done",
            }
        )
        ack = ws.receive_json()
        assert ack["status"] == "completed"
        # disconnect

    task = _reg.find_task_by_id(task_id)
    assert task.status == "completed"


def test_failed_task_unchanged_on_disconnect(admin_user):
    """already-failed task는 disconnect 후 그대로 failed이다 (failure_reason 불변)."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d6"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": False,
                "error_code": "SOME_ERR",
            }
        )
        ack = ws.receive_json()
        assert ack["status"] == "failed"

    task = _reg.find_task_by_id(task_id)
    assert task.status == "failed"
    assert task.failure_reason == "agent_error"  # disconnect로 덮어쓰면 안 됨


def test_disconnect_audit_task_requeued_event(admin_user):
    """첫 disconnect 처리 시 LOCAL_AGENT_TASK_REQUEUED audit 이벤트가 기록된다.

    2026-09-30: 기존엔 첫 disconnect부터 LOCAL_AGENT_TASK_FAILED였으나, 재큐잉-재시도
    도입 후 첫 disconnect는 REQUEUED로 기록되고 FAILED는 재시도 소진 후에만 발생한다
    (재시도 소진 케이스는 test_disconnect_fails_after_retries_exhausted 참고).
    """
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "open_url", {"url": "https://example.com/d7"})
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        # disconnect

    logs = _al.read_recent_logs(limit=200)
    disconnect_requeued = [
        e
        for e in logs
        if e["event_type"] == "LOCAL_AGENT_TASK_REQUEUED"
        and e.get("task_id") == task_id
        and "retry_count=1" in e.get("note", "")
    ]
    assert len(disconnect_requeued) >= 1


# ── Stage 11-6B: WS 상태 갱신 테스트 ──────────────────────────────────


def test_ws_auth_success_sets_last_seen_at(admin_user):
    """WS auth 성공 시 last_seen_at 갱신."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    a_before = _reg.get_agent(agent_id)
    assert a_before.last_seen_at == ""

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        a_after = _reg.get_agent(agent_id)
        assert a_after.last_seen_at != ""
        assert a_after.connected_at != ""
        assert a_after.disconnected_at == ""


def test_ws_heartbeat_updates_last_seen_at(admin_user):
    """heartbeat 수신 시 last_seen_at 갱신."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        first_seen = _reg.get_agent(agent_id).last_seen_at

        ws.send_json({"type": "heartbeat"})
        assert ws.receive_json()["type"] == "heartbeat_ack"
        second_seen = _reg.get_agent(agent_id).last_seen_at
        # 갱신됐거나 같은 시각 (동일 ms 내)
        assert second_seen >= first_seen


def test_ws_disconnect_sets_disconnected_at(admin_user):
    """WS disconnect 시 disconnected_at 설정."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

    a = _reg.get_agent(agent_id)
    assert a.disconnected_at != ""


# ── ws_noop: WS delivery path 검증 전용 no-op ─────────────────────────


def test_ws_noop_in_action_risk():
    """ws_noop 이 ACTION_RISK 에 low 로 등록되어 있어야 한다."""
    from ai_orchestrator.agent_hub.registry.facade import ACTION_RISK

    assert ACTION_RISK.get("ws_noop") == "low"


def test_ws_noop_not_in_server_auto_complete():
    """ws_noop 은 _SERVER_AUTO_COMPLETE 에 절대 포함되면 안 된다."""
    import ai_orchestrator.agent_hub.registry.facade as _reg

    assert "ws_noop" not in _reg._SERVER_AUTO_COMPLETE


def test_ws_noop_in_auto_execute_via_agent():
    """ws_noop 은 서버 측 AUTO_EXECUTE_VIA_AGENT 에 포함되어야 한다."""
    from ai_orchestrator.agent_hub.registry.facade import AUTO_EXECUTE_VIA_AGENT

    assert "ws_noop" in AUTO_EXECUTE_VIA_AGENT


def test_ws_noop_in_client_auto_execute():
    """ws_noop 은 클라이언트 _AUTO_EXECUTE_VIA_AGENT 에 포함되어야 한다."""
    from core.agent_runtime.connection.websocket_client import _AUTO_EXECUTE_VIA_AGENT

    assert "ws_noop" in _AUTO_EXECUTE_VIA_AGENT


def test_ws_noop_action_handler_no_side_effect():
    """ws_noop handler 는 외부 동작 없이 success=True, summary='ws_noop_ok' 반환."""
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("ws_noop", {})
    assert result.success is True
    assert result.summary == "ws_noop_ok"
    assert result.error == ""
    assert result.error_code == ""


def test_ws_noop_action_handler_ignores_payload():
    """ws_noop handler 는 임의 payload 가 있어도 동일한 결과를 반환한다."""
    from core.agent_runtime.connection.actions import execute_action

    result = execute_action("ws_noop", {"arbitrary_key": "arbitrary_value"})
    assert result.success is True
    assert result.summary == "ws_noop_ok"


def test_client_process_task_ws_noop_returns_success():
    """process_task 에서 ws_noop 이 success=True result 메시지를 반환한다."""
    from core.agent_runtime.connection.websocket_client import process_task

    r = process_task(
        {
            "task_id": "t-noop-1",
            "action": "ws_noop",
            "risk_level": "low",
            "params": {},
        }
    )
    assert r["type"] == "result"
    assert r["task_id"] == "t-noop-1"
    assert r["success"] is True
    assert r["error_code"] == ""


def test_ws_noop_full_delivery_path(admin_user):
    """ws_noop 이 queued → delivered → running → completed WS 경로를 완주한다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue(client, agent_id, "ws_noop")
    assert created["status"] == "queued", f"expected queued, got {created['status']}"
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == task_id
        assert msg["task"]["action"] == "ws_noop"

        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": "ws_noop_ok",
            }
        )
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"
        assert ack["status"] == "completed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "completed"
    assert fetched["started_at"]
    assert fetched["completed_at"]


def test_ws_noop_enqueue_does_not_auto_complete(admin_user):
    """ws_noop enqueue 결과는 completed 가 아니라 queued 여야 한다.
    (_SERVER_AUTO_COMPLETE 에 포함됐다면 즉시 completed 로 반환된다.)
    """
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue(client, agent_id, "ws_noop")
    assert created["status"] == "queued"


def test_existing_actions_unchanged():
    """ping/system_info/list_allowed_apps 동작이 ws_noop 추가 후에도 불변이다."""
    from core.agent_runtime.connection.actions import execute_action

    assert execute_action("ping", {}).summary == "pong"
    assert execute_action("system_info", {}).success is True
    assert execute_action("list_allowed_apps", {}).success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ── 큐 등록 즉시 push (heartbeat 대기 없음) ────────────────────────────────


def test_ws_enqueue_pushes_immediately_without_pull(admin_user):
    """연결 중 enqueue 된 task 는 pull/heartbeat 없이도 즉시 task 메시지로 도착한다(대기 8초 → 즉시)."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"

        created = _enqueue(client, agent_id, "open_url", {"url": "https://example.org/wake"})

        msg = ws.receive_json()  # pull 을 보내지 않았다
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == created["task_id"]


def test_ws_wake_registry_cleared_on_disconnect(admin_user):
    import ai_orchestrator.agent_hub.router.ws as _ws

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        _enqueue(client, agent_id, "open_url", {"url": "https://example.org/x"})
        ws.receive_json()
        assert agent_id in _ws._WAKE
    assert agent_id not in _ws._WAKE


def test_enqueue_listener_failure_does_not_block_enqueue(admin_user):
    import ai_orchestrator.agent_hub.registry.facade as _reg
    import ai_orchestrator.agent_hub.registry.task_queue as _tq

    def _boom(_agent_id: str) -> None:
        raise RuntimeError("listener down")

    _tq._enqueue_listeners.append(_boom)
    try:
        client = _make_test_client(admin_user)
        agent_id, _ = _register(client)
        created = _enqueue(client, agent_id, "open_url", {"url": "https://example.org/y"})
        assert created["status"] == "queued"
        assert _reg.get_task(agent_id, created["task_id"]) is not None
    finally:
        _tq._enqueue_listeners.remove(_boom)
