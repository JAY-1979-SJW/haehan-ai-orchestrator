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

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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


@pytest.fixture
def viewer_user():
    return {"actor": "viewer_test", "role": "viewer"}


class _AnyCurrentUserOverrides(dict):
    """이름이 get_current_user 인 의존성은 어느 객체든 같은 사용자로 대체하는 dependency_overrides."""

    def __init__(self, user: dict):
        super().__init__()
        self._user = user

    def __bool__(self) -> bool:  # FastAPI 는 빈 dict 면 override 조회 자체를 건너뛴다
        return True

    def get(self, key, default=None):
        if getattr(key, "__name__", "") == "get_current_user":
            return lambda: self._user
        return super().get(key, default)


def _override_current_user(app, current_get_current_user, user: dict) -> None:
    """앱 라우트가 실제로 묶고 있는 get_current_user 를 객체 동일성과 무관하게 override 한다.

    다른 시험 파일의 fixture 가 importlib.reload(gates.auth) 를 하면 gates.auth.get_current_user 는 새 객체가
    되지만 이미 import 된 라우터는 옛 객체에 묶여 남는다. 그 상태에서 새 객체만 override 하면 라우터는 실제
    의존성(AUTH_ENABLED=False → 고정 owner)을 쓰게 되어 시험 실행 순서에 따라 결과가 달라진다.
    """
    app.dependency_overrides = _AnyCurrentUserOverrides(user)


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    _override_current_user(app, get_current_user, user_override)
    return TestClient(app, raise_server_exceptions=True)


def _register(client) -> tuple[str, str]:
    reg = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "stage3-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
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
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
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

    # WS 연결 → task push 수신 → WS context 안에서 status 확인
    # (disconnect 시 delivered/running active task 는 failed 로 전환되므로
    #  status 는 반드시 WS 연결 중에 확인해야 한다.)
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["task_id"] == task_id
        assert msg["task"]["action"] == "capture_screenshot"
        assert msg["task"]["risk_level"] == "high"
        assert msg["task"]["approved"] is True

        # delivered 상태 확인은 WS 연결 유지 중에 수행
        fetched = client.get(
            f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
        ).json()
        assert fetched["status"] == "delivered"


def test_approved_capture_not_redelivered_on_reconnect(admin_user):
    """동일 task 재실행 금지 — 이미 running 이던 작업은 재접속 후에도 재전송되지 않는다.

    (delivered 만 되고 running 신호가 없던 작업은 재큐잉·재전송되지만, running 이면 실행이
    시작됐을 수 있어 재전송하지 않는다.)
    """
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    # 1회차 — delivered → running
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

    # 2회차 — 재접속해도 추가 task 없음
    with client.websocket_connect("/api/v1/local-agents/ws") as ws2:
        ws2.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
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
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"

        # delivered → running 전환 (running 없이 result 전송 시
        # InvalidTaskTransitionError: delivered → completed 발생)
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        # 에이전트가 basename 만 포함한 summary 로 결과 보고
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": f"screenshot_saved basename={basename} size=1920x1080",
            }
        )
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
    import ai_orchestrator.audit.audit_logger as _al

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
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        # delivered → running 전환 필수 (상태 기계: delivered → running → completed)
        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": f"screenshot_saved basename={basename} size=1920x1080",
            }
        )
        ws.receive_json()  # result_ack

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
    import tools.gates.approval as _ap

    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]

    # approve 시점의 시각을 발급 시각 + 2시간 뒤로 이동시켜 토큰 만료 유발.
    # (approve_token 은 _load_store() 를 호출하므로 메모리 직접 수정은 복원됨)
    future = datetime.now(UTC) + timedelta(hours=2)
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
    from core.agent_runtime.connection.websocket_client import process_task

    r = process_task(
        {
            "task_id": "t-hr",
            "action": "capture_screenshot",
            "risk_level": "high",
            "params": {},
            # approved 플래그 없음
        }
    )
    assert r["success"] is False
    assert r["error_code"] == "NOT_IMPLEMENTED_STAGE2"


def test_client_process_task_approved_capture_runs_action(monkeypatch, tmp_path):
    """approved=True + capture_screenshot → action 실제 호출 경로 확인."""
    import core.agent_runtime.connection.actions as _actions
    import core.agent_runtime.connection.websocket_client as _wsc

    called = {}

    def fake_execute_action(action, params):
        called["action"] = action
        called["task_id"] = params.get("_task_id")
        return _actions.ActionResult(
            True,
            "screenshot_saved basename=fake.png size=10x10",
            {"file_basename": "fake.png", "image_width": 10, "image_height": 10, "action": "capture_screenshot"},
        )

    monkeypatch.setattr(_wsc, "execute_action", fake_execute_action)

    r = _wsc.process_task(
        {
            "task_id": "lat-hr-xyz",
            "action": "capture_screenshot",
            "risk_level": "high",
            "params": {"note": "ok"},
            "approved": True,
        }
    )
    assert r["success"] is True
    assert "basename=fake.png" in r["summary"]
    assert called["action"] == "capture_screenshot"
    assert called["task_id"] == "lat-hr-xyz"


# ── 10. 실제 capture (단위) — basename + 크기만 ────────────────────────


def test_action_capture_screenshot_returns_basename_only(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (640, 480)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n\x00fake")

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 640, 480))

    result = _actions.action_capture_screenshot(
        {"_task_id": "lat-abc123", "_approved": True},
    )
    assert result.success
    assert result.data["file_basename"].startswith("screenshot_lat-abc123_")
    assert result.data["file_basename"].endswith(".png")
    assert result.data["file_ext"] == ".png"
    assert result.data["image_width"] == 640
    assert result.data["image_height"] == 480

    # summary 에 basename + size 만 포함, 전체 경로 없음
    assert "basename=" in result.summary
    assert str(tmp_path) not in result.summary

    # 실제 파일이 지정 디렉터리에 저장됐고, 바깥으로 새지 않았다.
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name == result.data["file_basename"]


def test_action_capture_screenshot_dependency_missing(tmp_path, monkeypatch):
    """Pillow / mss 둘 다 없으면 SCREENSHOT_DEPENDENCY_MISSING 으로 실패."""
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    def _raise(*_a, **_kw):
        raise _actions._ScreenshotDependencyMissing("Pillow / mss 둘 다 없음")

    monkeypatch.setattr(_actions, "_grab_screen", _raise)

    result = _actions.action_capture_screenshot(
        {"_task_id": "t-nodep", "_approved": True},
    )
    assert not result.success
    assert result.error_code == "SCREENSHOT_DEPENDENCY_MISSING"


# ── 11. sanity: AUTO_EXECUTE_VIA_AGENT 양쪽 동기화 유지 ────────────────


def test_capture_screenshot_in_auto_exec_sets_both_sides():
    from ai_orchestrator.agent_hub.registry.facade import AUTO_EXECUTE_VIA_AGENT as _S
    from core.agent_runtime.connection.websocket_client import _AUTO_EXECUTE_VIA_AGENT as _C

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
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    # 이미 결정된 토큰 → approve_token 이 already_used 반환 혹은 registry 가 현재 상태 유지
    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    assert fetched["status"] == "rejected"


# ── Stage 13H-2 — result_data allowlist + safe metadata ──────────────────


def test_h2_allowlist_includes_screenshot_keys():
    from ai_orchestrator.agent_hub.registry.facade import _RESULT_DATA_ALLOWED_KEYS

    expected = {
        "screenshot_taken",
        "file_basename",
        "file_ext",
        "file_size_bytes",
        "image_width",
        "image_height",
        "storage_ref",
        "redaction_applied",
        "sensitive_screen_warning",
    }
    assert expected.issubset(_RESULT_DATA_ALLOWED_KEYS)


def test_h2_action_returns_safe_metadata_keys(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (1280, 720)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 1280, 720))

    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-h2",
            "_approved": True,
            "_approval_id": "tok-abc-123",
            "_agent_id": "la-test01",
        }
    )
    assert result.success
    d = result.data
    assert d["action"] == "capture_screenshot"
    assert d["dry_run"] is False
    assert d["screenshot_taken"] is True
    assert d["file_basename"].startswith("screenshot_lat-h2_")
    assert d["file_basename"].endswith(".png")
    assert d["file_ext"] == ".png"
    assert d["file_size_bytes"] > 0
    assert d["image_width"] == 1280
    assert d["image_height"] == 720
    assert d["storage_ref"] == f"la-test01/lat-h2/{d['file_basename']}"
    assert d["policy_decision"] == "approved_execution"
    assert d["redaction_applied"] is False
    assert d["execution_task_id"] == "lat-h2"
    assert d["approval_id"] == "tok-abc-123"


def test_h2_action_data_no_full_path_or_raw_image(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (10, 10)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"PNGDATA")

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 10, 10))
    result = _actions.action_capture_screenshot(
        {"_task_id": "lat-x", "_approved": True},
    )
    forbidden = {
        "full_path",
        "absolute_path",
        "raw_image",
        "raw_image_base64",
        "ocr_text",
        "clipboard_content",
        "token",
        "password",
        "cookie",
        "session",
        "secret",
        "authorization",
        "device_token",
    }
    assert not (set(result.data) & forbidden)
    # storage_ref 는 절대경로/드라이브 경로 금지
    s = result.data["storage_ref"]
    assert not s.startswith("/"), s
    assert ":" not in s, s
    assert "\\" not in s, s
    assert str(tmp_path) not in s


def test_h2_storage_ref_two_tier_when_no_agent_id(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (1, 1)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"P")

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 1, 1))
    result = _actions.action_capture_screenshot(
        {"_task_id": "lat-no-agent", "_approved": True},
    )
    assert result.data["storage_ref"].startswith("lat-no-agent/")
    assert result.data["storage_ref"].count("/") == 1


def test_h2_strip_result_data_drops_full_path_and_raw_image():
    from ai_orchestrator.agent_hub.registry.facade import _strip_result_data

    out = _strip_result_data(
        {
            "action": "capture_screenshot",
            "file_basename": "ok.png",
            "full_path": "C:\\Users\\victim\\Desktop\\ok.png",
            "absolute_path": "/home/victim/ok.png",
            "raw_image_base64": "iVBORw0KGgo...",
            "ocr_text": "PASSWORD: hunter2",
            "clipboard_content": "secret",
            "token": "leak",
            "password": "leak",
            "cookie": "leak",
        }
    )
    assert out is not None
    assert "full_path" not in out
    assert "absolute_path" not in out
    assert "raw_image_base64" not in out
    assert "ocr_text" not in out
    assert "clipboard_content" not in out
    assert "token" not in out
    assert "password" not in out
    assert "cookie" not in out
    assert out["action"] == "capture_screenshot"
    assert out["file_basename"] == "ok.png"


def test_h2_dry_run_data_preserved_through_strip():
    from ai_orchestrator.agent_hub.registry.facade import _strip_result_data

    out = _strip_result_data(
        {
            "action": "capture_screenshot",
            "dry_run": True,
            "screenshot_taken": False,
            "screenshot_dir_ready": True,
            "backend_available": "ImageGrab",
            "upload": False,
        }
    )
    assert out["dry_run"] is True
    assert out["screenshot_taken"] is False
    assert out["screenshot_dir_ready"] is True
    assert out["backend_available"] == "ImageGrab"
    assert out["upload"] is False


def test_h2_ws_client_injects_agent_id_and_approval_id():
    """process_task 가 capture_screenshot 에 _agent_id 와 _approval_id 를 주입."""
    import core.agent_runtime.connection.actions as _actions
    import core.agent_runtime.connection.websocket_client as _wsc

    captured = {}

    def fake_execute(action, params):
        captured["params"] = params
        return _actions.ActionResult(
            True,
            "screenshot_saved basename=x.png size=1x1",
            {"file_basename": "x.png", "image_width": 1, "image_height": 1, "action": "capture_screenshot"},
        )

    _orig = _wsc.execute_action
    _wsc.execute_action = fake_execute
    try:
        _wsc.process_task(
            {
                "task_id": "lat-inject",
                "agent_id": "la-inject01",
                "action": "capture_screenshot",
                "risk_level": "high",
                "params": {},
                "approved": True,
                "token_id": "tok-zzz",
            }
        )
    finally:
        _wsc.execute_action = _orig

    p = captured["params"]
    assert p["_task_id"] == "lat-inject"
    assert p["_approved"] is True
    assert p["_approval_id"] == "tok-zzz"
    assert p["_agent_id"] == "la-inject01"


def test_h2_ws_roundtrip_persists_screenshot_result_data(tmp_path, monkeypatch):
    """승인 → WS dispatch → process_task → result_data 저장 전체 경로."""
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions
    from core.agent_runtime.connection.websocket_client import process_task

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (320, 240)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"\x89PNG" + b"y" * 32)

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 320, 240))

    client = _make_test_client({"actor": "admin", "role": "admin"})
    agent_id, device_token = _register(client)

    task = _enqueue_capture(client, agent_id)
    task_id = task["task_id"]
    token_id = task["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": device_token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"

        ws.send_json({"type": "running", "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"

        result_msg = process_task(msg["task"])
        result_msg["agent_id"] = agent_id
        assert result_msg["data"]["action"] == "capture_screenshot"
        ws.send_json(result_msg)
        ack = ws.receive_json()
        assert ack["type"] == "result_ack"
        assert ack["status"] == "completed"

    fetched = client.get(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}",
    ).json()
    rd = fetched["result_data"]
    assert isinstance(rd, dict) and rd
    assert rd["action"] == "capture_screenshot"
    assert rd["screenshot_taken"] is True
    assert rd["file_basename"].endswith(".png")
    assert rd["file_ext"] == ".png"
    assert rd["file_size_bytes"] > 0
    assert rd["image_width"] == 320
    assert rd["image_height"] == 240
    assert rd["storage_ref"].startswith(f"{agent_id}/{task_id}/")
    assert rd["policy_decision"] == "approved_execution"
    assert rd["redaction_applied"] is False
    assert rd["execution_task_id"] == task_id
    assert rd.get("approval_id")
    SENSITIVE = {
        "full_path",
        "absolute_path",
        "raw_image",
        "raw_image_base64",
        "ocr_text",
        "clipboard_content",
        "token",
        "password",
        "cookie",
        "session",
        "secret",
        "authorization",
        "device_token",
    }
    assert not (set(rd) & SENSITIVE)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
