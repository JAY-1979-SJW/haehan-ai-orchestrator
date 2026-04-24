"""Stage 3 — capture_screenshot 승인 게이트 + 로컬 1회 실행 통합 검증.

요구 테스트:
  1. 승인 전 capture_screenshot 은 status=waiting_approval.
  2. 승인 전에는 WS 로 push 되지 않는다 (queued 큐에 미포함).
  3. 승인 성공 시 waiting_approval → queued 로 전환.
  4. 승인 후 WS dispatch 페이로드에 approved=True 가 포함돼 1회 전달된다.
  5. 결과 summary 에 basename 만 포함되고 전체 경로가 없다.
  6. 전체 경로 / 승인 token 원문이 감사 로그에 노출되지 않는다.
  7. 재승인 / 중복 실행 방지 — 두 번째 승인 호출은 현재 상태만 반환, queued 다시 push 안 됨.
  8. 만료된 토큰으로 승인 시도하면 task 가 rejected 로 종결 (실행 불가).
  9. 클라이언트 process_task 는 approved 플래그 없을 때 NOT_IMPLEMENTED_STAGE2 유지.
 10. 실제 capture (local_agent/actions.action_capture_screenshot) 가 basename + 크기만 반환.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    import importlib
    import ai_orchestrator.auth as _auth; importlib.reload(_auth)
    import ai_orchestrator.local_agent_router as _lar; importlib.reload(_lar)

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
    return {"actor": "admin_test", "role": "admin"}


@pytest.fixture
def viewer_user():
    return {"actor": "viewer_test", "role": "viewer"}


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from ai_orchestrator.local_agent_router import local_agent_router
    from ai_orchestrator.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _register(client) -> tuple[str, str]:
    reg = client.post("/api/v1/local-agents/register", json={
        "host": "stage3-test", "os_name": "Windows 11", "version": "0.1.0",
    }).json()
    return reg["agent_id"], reg["device_token"]


def _enqueue_capture(client, agent_id: str) -> dict:
    return client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={"action": "capture_screenshot"},
    ).json()


# ── 1. 승인 전 waiting_approval ─────────────────────────────────────────

def test_capture_screenshot_initial_status_is_waiting_approval(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    task = _enqueue_capture(client, agent_id)
    assert task["risk_level"] == "high"
    assert task["status"] == "waiting_approval"
    assert task["token_id"]
    assert task["approved_at"] == ""
    assert task["approved_by"] == ""


# ── 2. 승인 전에는 WS 로 전달되지 않음 ─────────────────────────────────

def test_unapproved_capture_not_delivered_via_ws(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id,
                      "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        ws.send_json({"type": "heartbeat"})
        assert ws.receive_json()["type"] == "heartbeat_ack"
        ws.send_json({"type": "pull"})
        ws.send_json({"type": "heartbeat"})
        # heartbeat_ack 만 오고 task 는 오지 않아야 한다
        next_msg = ws.receive_json()
        assert next_msg["type"] == "heartbeat_ack"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "waiting_approval"


# ── 3. 승인 성공 → queued ──────────────────────────────────────────────

def test_approval_transitions_waiting_to_queued(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    approve_resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert approve_resp.status_code == 200, approve_resp.text
    data = approve_resp.json()
    assert data["status"] == "queued"
    assert data["approved_at"]
    assert data["approved_by"] == "admin_test"


def test_approval_requires_token_id(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": ""},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "MISSING_TOKEN_ID"


def test_approve_wrong_token_id_fails(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code in (400, 404)  # not_found / task_mismatch → 404/400

    # task 는 그대로 waiting_approval
    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "waiting_approval"


def test_viewer_cannot_approve(admin_user, viewer_user):
    admin_client = _make_test_client(admin_user)
    agent_id, _ = _register(admin_client)
    created = _enqueue_capture(admin_client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    viewer_client = _make_test_client(viewer_user)
    r = viewer_client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r.status_code == 403


# ── 4. 승인 후 WS dispatch 에 approved=True + 1회 전달 ────────────────

def test_approved_capture_dispatched_via_ws_with_approved_flag(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    # 승인
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    # WS 연결 → task push 수신
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id,
                      "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == task_id
        assert msg["task"]["action"] == "capture_screenshot"
        assert msg["task"]["risk_level"] == "high"
        assert msg["task"]["approved"] is True

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "delivered"


def test_approved_capture_not_redelivered_on_reconnect(admin_user):
    """동일 task 재실행 금지 — 이미 delivered 된 작업은 재접속 후에도 재전송되지 않는다."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    # 1회차 — delivered
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id,
                      "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

    # 2회차 — 재접속해도 추가 task 없음
    with client.websocket_connect("/api/v1/local-agents/ws") as ws2:
        ws2.send_json({"type": "auth", "agent_id": agent_id,
                       "device_token": token})
        assert ws2.receive_json()["type"] == "auth_ok"
        ws2.send_json({"type": "heartbeat"})
        assert ws2.receive_json()["type"] == "heartbeat_ack"
        ws2.send_json({"type": "heartbeat"})
        # 재배송 없음
        assert ws2.receive_json()["type"] == "heartbeat_ack"


# ── 5. 결과 summary 에 basename 만, 전체 경로 없음 ────────────────────

def test_result_summary_contains_basename_only(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    basename = f"screenshot_{task_id[-12:]}_abc.png"
    full_path = f"C:/Users/secret-user/some/hidden/dir/{basename}"

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id,
                      "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        # 에이전트가 basename 만 포함한 summary 로 결과 보고
        ws.send_json({
            "type": "result",
            "task_id": task_id,
            "success": True,
            "summary": f"screenshot_saved basename={basename} size=1920x1080",
        })
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"
        assert ack["status"] == "completed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert basename in fetched["result_summary"]
    # 전체 경로는 서버에 저장되지 않아야 한다
    assert full_path not in fetched["result_summary"]
    assert "C:/Users/secret-user" not in fetched["result_summary"]


# ── 6. 감사 로그에 전체 경로 / token 원문 미노출 ───────────────────────

def test_audit_log_does_not_leak_fullpath_or_token(admin_user):
    import ai_orchestrator.audit_logger as _al
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    basename = f"screenshot_{task_id}_xyz.png"
    synthetic_fullpath = "C:/Users/secret-user/.haehan_agent/screenshots/" + basename
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id,
                      "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({
            "type": "result", "task_id": task_id, "success": True,
            "summary": f"screenshot_saved basename={basename} size=1920x1080",
        })
        ws.receive_json()

    raw = _al._LOG_PATH.read_text(encoding="utf-8")
    # device_token 원문은 등장 불가
    assert token not in raw
    # 전체 경로 패턴은 등장 불가
    assert synthetic_fullpath not in raw
    assert "C:/Users/secret-user" not in raw


# ── 7. 중복 승인 / 재실행 방지 ─────────────────────────────────────────

def test_double_approve_is_idempotent(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    r1 = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r1.status_code == 200
    first_approved_at = r1.json()["approved_at"]

    # 두 번째 승인 호출 — 상태 그대로, approved_at 변경 없음
    r2 = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r2.status_code == 200
    assert r2.json()["approved_at"] == first_approved_at


# ── 8. 만료 토큰 → rejected ────────────────────────────────────────────

def test_expired_token_rejects_task(admin_user, monkeypatch):
    import ai_orchestrator.approval as _ap
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    # approve 시점의 시각을 발급 시각 + 2시간 뒤로 이동시켜 토큰 만료 유발.
    # (approve_token 은 _load_store() 를 호출하므로 메모리 직접 수정은 복원됨)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    monkeypatch.setattr(_ap, "_now", lambda: future)

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r.status_code in (410, 400)

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "rejected"
    assert fetched["reject_reason"] == "token_expired"


# ── 9. 클라이언트 process_task — 미승인 high risk 는 NOT_IMPLEMENTED_STAGE2 ───

def test_client_process_task_high_risk_without_approved_flag():
    from local_agent.websocket_client import process_task
    r = process_task({
        "task_id": "t-hr",
        "action": "capture_screenshot",
        "risk_level": "high",
        "params": {},
        # approved 플래그 없음
    })
    assert r["success"] is False
    assert r["error_code"] == "NOT_IMPLEMENTED_STAGE2"


def test_client_process_task_approved_capture_runs_action(monkeypatch, tmp_path):
    """approved=True + capture_screenshot → action 실제 호출 경로 확인."""
    import local_agent.actions as _actions
    import local_agent.websocket_client as _wsc

    called = {}

    def fake_execute_action(action, params):
        called["action"] = action
        called["task_id"] = params.get("_task_id")
        return _actions.ActionResult(
            True, "screenshot_saved basename=fake.png size=10x10",
            {"screenshot_file": "fake.png", "width": 10, "height": 10},
        )

    monkeypatch.setattr(_wsc, "execute_action", fake_execute_action)

    r = _wsc.process_task({
        "task_id": "lat-hr-xyz",
        "action": "capture_screenshot",
        "risk_level": "high",
        "params": {"note": "ok"},
        "approved": True,
    })
    assert r["success"] is True
    assert "basename=fake.png" in r["summary"]
    assert called["action"] == "capture_screenshot"
    assert called["task_id"] == "lat-hr-xyz"


# ── 10. 실제 capture (단위) — basename + 크기만 ────────────────────────

def test_action_capture_screenshot_returns_basename_only(tmp_path, monkeypatch):
    import local_agent.actions as _actions
    import local_agent.config as _cfg

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (640, 480)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n\x00fake")

    monkeypatch.setattr(_actions, "_grab_screen",
                        lambda: (_FakeImg(), 640, 480))

    result = _actions.action_capture_screenshot(
        {"_task_id": "lat-abc123", "_approved": True},
    )
    assert result.success
    assert result.data["screenshot_file"].startswith("screenshot_lat-abc123_")
    assert result.data["screenshot_file"].endswith(".png")
    assert result.data["width"] == 640
    assert result.data["height"] == 480

    # summary 에 basename + size 만 포함, 전체 경로 없음
    assert "basename=" in result.summary
    assert str(tmp_path) not in result.summary

    # 실제 파일이 지정 디렉터리에 저장됐고, 바깥으로 새지 않았다.
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == result.data["screenshot_file"]


def test_action_capture_screenshot_dependency_missing(tmp_path, monkeypatch):
    """Pillow / mss 둘 다 없으면 SCREENSHOT_DEPENDENCY_MISSING 으로 실패."""
    import local_agent.actions as _actions
    import local_agent.config as _cfg

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    def _raise(*_a, **_kw):
        raise _actions._ScreenshotDependencyMissing(
            "Pillow / mss 둘 다 없음")

    monkeypatch.setattr(_actions, "_grab_screen", _raise)

    result = _actions.action_capture_screenshot(
        {"_task_id": "t-nodep", "_approved": True},
    )
    assert not result.success
    assert result.error_code == "SCREENSHOT_DEPENDENCY_MISSING"


# ── 11. sanity: AUTO_EXECUTE_VIA_AGENT 양쪽 동기화 유지 ────────────────

def test_capture_screenshot_in_auto_exec_sets_both_sides():
    from ai_orchestrator.local_agent_registry import AUTO_EXECUTE_VIA_AGENT as _S
    from local_agent.websocket_client import _AUTO_EXECUTE_VIA_AGENT as _C
    assert "capture_screenshot" in _S
    assert "capture_screenshot" in _C
    assert set(_S) == set(_C)


# ── 12. 거절 (reject) — waiting_approval → rejected ───────────────────

def test_reject_transitions_to_rejected(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/reject",
        json={"token_id": token_id, "reason": "security review"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "rejected"
    assert data["reject_reason"] == "security review"


def test_reject_then_approve_not_allowed(admin_user):
    """거절된 작업은 이후 승인 시도해도 상태 변경 불가 (재실행 방지)."""
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/reject",
        json={"token_id": token_id},
    )
    # 이후 승인 시도
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    # 이미 결정된 토큰 → approve_token 이 already_used 반환 혹은 registry 가 현재 상태 유지
    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "rejected"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
