"""capture_screenshot dry-run + 실제 실행 사전 방어 + 감사 이벤트 검증.

필수:
  1. dry_run=true → 실제 png 파일 생성 없음
  2. dry-run 결과에 전체 경로 없음 (basename/경로 미포함)
  3. dry-run 결과에 upload=false 포함
  4. backend 없음 상태에서도 dry-run 은 dependency 상태만 보고 (success=True)
  5. approved 플래그 없는 실제 capture → SCREENSHOT_NOT_APPROVED 거절
  6. _task_id 없는 실제 capture → SCREENSHOT_MISSING_TASK_ID 거절
  7. 실제 실행 결과는 basename 만 포함 (이미 기존 테스트에서 검증, 회귀 확인)
  8. 감사 로그에 CAPTURE_SCREENSHOT_* 이벤트가 남는다
     (APPROVAL_REQUESTED / APPROVED / DRY_RUN_COMPLETED / COMPLETED / FAILED / REJECTED)

모든 테스트는 실제 브라우저/외부 앱/네트워크 호출 없이 실행된다.
"""

from __future__ import annotations

import sys
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
            "host": "dry-run-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
    return reg["agent_id"], reg["device_token"]


# ── 1/2/3. dry-run 단위 동작 검증 (action 레벨) ────────────────────────


def test_dry_run_does_not_create_any_png_file(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    # 실제 grab 이 호출되면 명시적 FAIL
    def _must_not_grab():
        raise AssertionError("dry-run 모드에서 _grab_screen 호출 금지")

    monkeypatch.setattr(_actions, "_grab_screen", _must_not_grab)

    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-dry1",
            "_approved": True,
            "options": {"dry_run": True},
        }
    )
    assert result.success
    # 디렉터리는 존재해도 되지만 png 파일은 생성되지 않아야 한다
    pngs = list(tmp_path.rglob("*.png"))
    assert pngs == [], f"dry-run 에서 PNG 파일이 생성됨: {pngs}"


def test_dry_run_summary_has_no_full_path_or_basename(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_ for _ in ()).throw(AssertionError("no-grab")))

    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-dry2",
            "_approved": True,
            "options": {"dry_run": True},
        }
    )
    assert result.success
    # 전체 경로 금지
    assert str(tmp_path) not in result.summary
    # basename 도 나오면 안 된다 (dry-run 이 PNG 를 만들지 않았으므로)
    assert "screenshot_lat-dry2_" not in result.summary
    assert ".png" not in result.summary
    # data 에도 screenshot_file / path 가 없다
    assert "screenshot_file" not in result.data
    assert "path" not in result.data


def test_dry_run_summary_contains_upload_false(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)
    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-dry3",
            "_approved": True,
            "options": {"dry_run": True},
        }
    )
    assert result.success
    assert "dry_run:true" in result.summary
    assert "upload:false" in result.summary
    assert result.data["upload"] is False
    assert result.data["dry_run"] is True
    assert "screenshot_dir_ready" in result.data
    assert "backend_available" in result.data


# ── 4. backend none 상태에서도 dry-run 성공 ────────────────────────────


def test_dry_run_reports_backend_none_gracefully(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(_actions, "_detect_backend", lambda: "none")

    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-dry4",
            "_approved": True,
            "options": {"dry_run": True},
        }
    )
    assert result.success
    assert "backend_available:none" in result.summary
    assert result.data["backend_available"] == "none"
    # 실패가 아님 — dry-run 은 dependency 상태만 보고


# ── 5. approved 없음 → 실제 capture 거절 ───────────────────────────────


def test_real_capture_without_approved_flag_is_rejected(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)
    # _grab_screen 은 호출되지 말아야 한다
    monkeypatch.setattr(
        _actions, "_grab_screen", lambda: (_ for _ in ()).throw(AssertionError("approved 없이 grab 호출 금지"))
    )

    # dry_run 없음 + _approved 없음 → 즉시 거절
    r = _actions.action_capture_screenshot({"_task_id": "lat-no-approve"})
    assert not r.success
    assert r.error_code == "SCREENSHOT_NOT_APPROVED"
    assert list(tmp_path.rglob("*.png")) == []

    # False 로 명시해도 동일
    r2 = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-no-approve",
            "_approved": False,
        }
    )
    assert not r2.success
    assert r2.error_code == "SCREENSHOT_NOT_APPROVED"


# ── 6. _task_id 없음 → 실제 capture 거절 ───────────────────────────────


def test_real_capture_without_task_id_is_rejected(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(
        _actions, "_grab_screen", lambda: (_ for _ in ()).throw(AssertionError("task_id 없이 grab 호출 금지"))
    )

    r = _actions.action_capture_screenshot({"_approved": True})
    assert not r.success
    assert r.error_code == "SCREENSHOT_MISSING_TASK_ID"
    assert list(tmp_path.rglob("*.png")) == []

    # 공백 문자열도 동일하게 거절
    r2 = _actions.action_capture_screenshot(
        {"_approved": True, "_task_id": "   "},
    )
    assert not r2.success
    assert r2.error_code == "SCREENSHOT_MISSING_TASK_ID"


# ── 7. 실제 실행 결과는 basename 만 (회귀 확인) ────────────────────────


def test_real_capture_result_basename_only(tmp_path, monkeypatch):
    import core.agent_runtime.common.config as _cfg
    import core.agent_runtime.connection.actions as _actions

    monkeypatch.setattr(_cfg, "LOCAL_AGENT_SCREENSHOT_DIR", tmp_path)

    class _FakeImg:
        size = (1280, 720)

        def save(self, path, format="PNG"):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n\x00fake")

    monkeypatch.setattr(_actions, "_grab_screen", lambda: (_FakeImg(), 1280, 720))

    result = _actions.action_capture_screenshot(
        {
            "_task_id": "lat-real",
            "_approved": True,
        }
    )
    assert result.success
    assert "basename=" in result.summary
    assert str(tmp_path) not in result.summary
    # 결과 키는 file_basename(저장 경로가 아니라 파일 이름만) — 2026-10-05 시험이 옛 키 screenshot_file 을 기대해 실패하던 것
    assert result.data["file_basename"].endswith(".png")
    # 전체 경로가 result 에 새어나오지 않는다
    assert "/" not in result.data["file_basename"]
    assert "\\" not in result.data["file_basename"]
    assert str(tmp_path) not in " ".join(str(v) for v in result.data.values())


# ── 8. 감사 로그 이벤트 ────────────────────────────────────────────────


def _enqueue_capture(client, agent_id: str, dry_run: bool = False) -> dict:
    params = {"options": {"dry_run": True}} if dry_run else {}
    return client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={"action": "capture_screenshot", "params": params},
    ).json()


def _audit_events():
    import ai_orchestrator.audit.audit_logger as _al

    return [e["event_type"] for e in _al.read_recent_logs(limit=200)]


def test_audit_emits_approval_requested_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    _enqueue_capture(client, agent_id)
    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED" in events
    # 기존 이벤트도 유지
    assert "LOCAL_AGENT_TASK_WAITING_APPROVAL" in events


def test_audit_emits_approved_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r.status_code == 200
    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_APPROVED" in events


def test_audit_emits_rejected_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/reject",
        json={"token_id": token_id, "reason": "ops denial"},
    )
    assert r.status_code == 200
    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_REJECTED" in events


def test_audit_emits_dry_run_completed_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id, dry_run=True)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        # 에이전트는 실행 시작을 먼저 알린다(서버는 running 없이 delivered → completed 를 거부)
        ws.send_json({"type": "running", "agent_id": agent_id, "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        # 에이전트가 dry-run summary 로 완료 보고
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": ("dry_run:true screenshot_dir_ready:true backend_available:none upload:false"),
            }
        )
        assert ws.receive_json()["type"] == "result_ack"

    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED" in events
    # 일반 COMPLETED 이벤트는 이 작업에 대해 추가로 발생하지 않아야 한다
    assert "CAPTURE_SCREENSHOT_COMPLETED" not in events


def test_audit_emits_completed_event_for_real_capture(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id, dry_run=False)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        # 에이전트는 실행 시작을 먼저 알린다(서버는 running 없이 delivered → completed 를 거부)
        ws.send_json({"type": "running", "agent_id": agent_id, "task_id": task_id})
        assert ws.receive_json()["type"] == "running_ack"
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": ("screenshot_saved basename=screenshot_x_y.png size=10x10"),
            }
        )
        assert ws.receive_json()["type"] == "result_ack"

    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_COMPLETED" in events
    assert "CAPTURE_SCREENSHOT_DRY_RUN_COMPLETED" not in events


def test_audit_emits_failed_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    created = _enqueue_capture(client, agent_id)
    task_id = created["task_id"]
    token_id = created["token_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        assert ws.receive_json()["type"] == "task"
        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": False,
                "error_code": "SCREENSHOT_CAPTURE_FAILED",
                "error": "environment has no display",
                "summary": "capture_screenshot 실패",
            }
        )
        assert ws.receive_json()["type"] == "result_ack"

    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_FAILED" in events


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
