"""Stage 13H-2E: approval public_id / token_id 분리 회귀.

token_id 는 서버 내부 승인 검증용 secret-like 값이며, public_id 는
UI/result_data/audit 표시용 외부 식별자다. 본 테스트는:

  - ApprovalToken 발급 시 두 값이 다르고 public_id 가 "appr_" prefix
  - LocalAgentTask 에 attach_token 시 token_id, approval_public_id 모두 저장
  - to_safe() 에 approval_id (public) 포함, to_dispatch() 에 approval_id 만 포함
    (token_id 는 dispatch payload 에 노출 금지)
  - websocket_client process_task 가 approval_id 를 _approval_id 로 주입
  - approve endpoint 는 token_id 입력으로만 성공, public_id 입력은 거부
  - capture_screenshot result_data.approval_id 는 public_id 와 같고 token_id
    와 다름
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import ai_orchestrator.agent_hub.registry.facade as reg
import tools.gates.approval as _ap


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    # auth/local_agent_router 를 reload 하지 않는다: reload 하면 get_current_user 가 시험마다 새 객체가 되는데
    # 하위 라우터는 처음 import 된 옛 객체에 묶여 있어 dependency_overrides 가 두 번째 시험부터 안 먹혀
    # 파일 전체 실행 시 등록이 401 이 되고 KeyError: 'agent_id' 가 난다(단독 실행만 통과, 2026-10-04 확인).
    import ai_orchestrator.audit.audit_logger as _al

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")

    reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()
    yield
    reg.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


def _make_test_client(user):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def _admin():
    return {"actor": "admin", "role": "admin"}


def _register(client):
    r = client.post("/api/v1/local-agents/register", json={"host": "h", "os_name": "Windows", "version": "0.1"})
    body = r.json()
    return body["agent_id"], body["device_token"]


# ─────────────────────────────────────────────────────────────────────────
# 1. ApprovalToken 자체에 public_id 가 부여되고 token_id 와 다름
# ─────────────────────────────────────────────────────────────────────────


def test_approval_token_has_distinct_public_id():
    tok = _ap.issue_token_for_dev_reg("lat-x", "admin", "high")
    assert tok.token_id
    assert tok.public_id
    assert tok.public_id != tok.token_id
    assert tok.public_id.startswith("appr_")


# ─────────────────────────────────────────────────────────────────────────
# 2. attach_token 으로 task 에 token_id + approval_public_id 모두 저장
# ─────────────────────────────────────────────────────────────────────────


def test_attach_token_stores_both_ids():
    reg.clear()
    t = reg.enqueue_task(
        agent_id="la-x", action="capture_screenshot", params={"options": {"dry_run": True}}, requested_by="admin"
    )
    reg.attach_token(t.task_id, "tok-internal-1", "appr_public_1")
    fetched = reg.find_task_by_id(t.task_id)
    assert fetched.token_id == "tok-internal-1"  # noqa: S105 — 테스트용 식별자, 실제 비밀값 아님
    assert fetched.approval_public_id == "appr_public_1"


# ─────────────────────────────────────────────────────────────────────────
# 3. to_safe() 에 approval_id (public) 포함
# ─────────────────────────────────────────────────────────────────────────


def test_to_safe_exposes_approval_public_id():
    reg.clear()
    t = reg.enqueue_task(
        agent_id="la-x", action="capture_screenshot", params={"options": {"dry_run": True}}, requested_by="admin"
    )
    reg.attach_token(t.task_id, "tok-internal-2", "appr_public_2")
    safe = reg.find_task_by_id(t.task_id).to_safe()
    assert safe["approval_id"] == "appr_public_2"
    assert safe["approval_public_id"] == "appr_public_2"


# ─────────────────────────────────────────────────────────────────────────
# 4. to_dispatch() 에 token_id 미노출 + approval_id 노출
# ─────────────────────────────────────────────────────────────────────────


def test_to_dispatch_uses_public_id_not_token_id():
    reg.clear()
    t = reg.enqueue_task(
        agent_id="la-x", action="capture_screenshot", params={"options": {"dry_run": True}}, requested_by="admin"
    )
    reg.attach_token(t.task_id, "tok-secret-3", "appr_public_3")
    reg.mark_approved(t.task_id, "admin")
    payload = reg.find_task_by_id(t.task_id).to_dispatch()
    assert payload["approved"] is True
    assert payload.get("approval_id") == "appr_public_3"
    assert "token_id" not in payload


def test_to_dispatch_legacy_falls_back_to_token_id_when_public_missing():
    """1릴리즈 backward compat: public_id 없는 legacy task 도 dispatch 가능."""
    reg.clear()
    t = reg.enqueue_task(
        agent_id="la-x", action="capture_screenshot", params={"options": {"dry_run": True}}, requested_by="admin"
    )
    # public_id 누락 — legacy attach
    reg.attach_token(t.task_id, "tok-only-4")
    reg.mark_approved(t.task_id, "admin")
    payload = reg.find_task_by_id(t.task_id).to_dispatch()
    # legacy 경로는 token_id 를 fallback 으로 approval_id 키에 넣는다.
    assert payload["approval_id"] == "tok-only-4"
    assert "token_id" not in payload


# ─────────────────────────────────────────────────────────────────────────
# 5. websocket_client process_task: approval_id → _approval_id 주입
# ─────────────────────────────────────────────────────────────────────────


def test_process_task_injects_public_approval_id():
    import core.agent_runtime.connection.actions as _actions
    import core.agent_runtime.connection.websocket_client as _wsc

    captured = {}

    def fake_execute(action, params):
        captured["params"] = params
        return _actions.ActionResult(
            True,
            "ok",
            {"action": "capture_screenshot", "file_basename": "x.png", "image_width": 1, "image_height": 1},
        )

    orig = _wsc.execute_action
    _wsc.execute_action = fake_execute
    try:
        _wsc.process_task(
            {
                "task_id": "lat-pid",
                "agent_id": "la-pid",
                "action": "capture_screenshot",
                "risk_level": "high",
                "params": {},
                "approved": True,
                "approval_id": "appr_public_xyz",
            }
        )
    finally:
        _wsc.execute_action = orig

    p = captured["params"]
    assert p["_approval_id"] == "appr_public_xyz"


# ─────────────────────────────────────────────────────────────────────────
# 6. approve endpoint: token_id 만 성공, public_id 시도는 거부
# ─────────────────────────────────────────────────────────────────────────


def test_approve_with_token_id_succeeds_public_id_rejected():
    reg.clear()
    client = _make_test_client(_admin())
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    task_id = r.json()["task_id"]
    task = reg.get_task(agent_id, task_id)
    token_id = task.token_id
    public_id = task.approval_public_id
    assert token_id and public_id and token_id != public_id

    # public_id 만으로는 승인 불가 (404 not_found)
    bad = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": public_id},
    )
    assert bad.status_code == 404

    # token_id 로는 승인 성공
    ok = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "queued"


# ─────────────────────────────────────────────────────────────────────────
# 7. capture_screenshot result_data.approval_id == public_id, != token_id
# ─────────────────────────────────────────────────────────────────────────


def test_result_data_approval_id_is_public_id_not_token_id(tmp_path, monkeypatch):
    reg.clear()
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions
    from core.agent_runtime.connection.websocket_client import process_task

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (10, 10)

        def save(self, path, format="PNG"):
            from pathlib import Path as _P

            _P(path).write_bytes(b"\x89PNG_data")

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 10, 10))

    client = _make_test_client(_admin())
    agent_id, device_token = _register(client)

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False},
    )
    task_id = r.json()["task_id"]
    task = reg.get_task(agent_id, task_id)
    token_id = task.token_id
    public_id = task.approval_public_id

    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": device_token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        # WS dispatch payload 검사: token_id 없음, approval_id == public_id
        assert "token_id" not in msg["task"]
        assert msg["task"].get("approval_id") == public_id

        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        rmsg = process_task(msg["task"])
        rmsg["agent_id"] = agent_id
        ws.send_json(rmsg)
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    rd = fetched["result_data"]
    assert rd is not None
    assert rd.get("approval_id") == public_id
    assert rd.get("approval_id") != token_id


# ─────────────────────────────────────────────────────────────────────────
# 8. open_url_execute: result_data.approval_id == public_id
# ─────────────────────────────────────────────────────────────────────────


def test_open_url_execute_result_data_uses_public_id(tmp_path):
    reg.clear()
    from core.agent_runtime.connection.websocket_client import process_task

    client = _make_test_client(_admin())
    agent_id, device_token = _register(client)

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/open-url-execution-request",
        json={"url": "https://example.com/13h2e"},
    )
    task_id = r.json()["task_id"]
    task = reg.get_task(agent_id, task_id)
    token_id = task.token_id
    public_id = task.approval_public_id

    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    with mock.patch("core.agent_runtime.connection.actions.webbrowser.open"):
        with client.websocket_connect("/api/v1/local-agents/ws") as ws:
            ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": device_token})
            assert ws.receive_json()["type"] == "auth_ok"
            msg = ws.receive_json()
            assert "token_id" not in msg["task"]
            assert msg["task"].get("approval_id") == public_id

            ws.send_json({"type": "running", "task_id": task_id})
            assert ws.receive_json()["type"] == "running_ack"

            rmsg = process_task(msg["task"])
            rmsg["agent_id"] = agent_id
            ws.send_json(rmsg)
            assert ws.receive_json()["type"] == "result_ack"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    rd = fetched["result_data"]
    assert rd.get("approval_id") == public_id
    assert rd.get("approval_id") != token_id
