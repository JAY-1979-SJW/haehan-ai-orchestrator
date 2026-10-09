"""POST /local-agents/{agent_id}/capture-screenshot 운영자 요청 API 검증.

필수 테스트:
  1. body 있음 + dry_run 생략 → dry_run=true
  2. body 없음 → dry_run=true
  3. {} → dry_run=true
  4. {"reason": "..."} → dry_run=true
  5. dry_run=false 명시 → params.options.dry_run=false 저장
  6. 모든 요청이 waiting_approval 로 시작
  7. 응답에 approval token 원문 없음
  8. 응답에 device_token/secret/전체 경로/이미지 파일명 없음
  9. CAPTURE_SCREENSHOT_REQUEST_CREATED 이벤트 발생
 10. CAPTURE_SCREENSHOT_APPROVAL_REQUESTED 이벤트 유지
 11. 승인 전 WebSocket queued 에 포함되지 않음
 12. (기존 82개 별도 suite 에서 회귀 확인)
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
            "host": "req-api-test",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    ).json()
    return reg["agent_id"], reg["device_token"]


def _audit_events():
    import ai_orchestrator.audit.audit_logger as _al

    return [e["event_type"] for e in _al.read_recent_logs(limit=200)]


_RESPONSE_FIELDS = {
    "task_id",
    "agent_id",
    "action",
    "status",
    "dry_run",
    "approval_required",
}


# ── 1/2/3/4. 기본 dry_run=true 처리 ────────────────────────────────────


def test_default_request_with_explicit_body_uses_dry_run_true(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"reason": "operator_check"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is True
    assert data["status"] == "waiting_approval"
    assert data["action"] == "capture_screenshot"
    assert data["agent_id"] == agent_id
    assert data["approval_required"] is True


def test_request_without_body_uses_dry_run_true(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    # body 생략
    r = client.post(f"/api/v1/local-agents/{agent_id}/capture-screenshot")
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True


def test_request_empty_object_uses_dry_run_true(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True


def test_request_reason_only_uses_dry_run_true(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"reason": "monthly verification"},
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is True


# ── 5. dry_run=false 명시 ──────────────────────────────────────────────


def test_explicit_dry_run_false_stored_in_task_params(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False, "reason": "incident capture"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is False
    assert data["status"] == "waiting_approval"

    # task.params.options.dry_run == False 로 저장됐는지 GET 으로 재확인
    fetched = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{data['task_id']}").json()
    assert fetched["params"]["options"]["dry_run"] is False


def test_dry_run_true_stored_in_task_params(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    data = r.json()
    fetched = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{data['task_id']}").json()
    assert fetched["params"]["options"]["dry_run"] is True


# ── 6. 모든 요청이 waiting_approval 로 시작 ────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"reason": "x"},
        {"dry_run": True},
        {"dry_run": False},
    ],
)
def test_all_requests_start_in_waiting_approval(admin_user, body):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    kwargs = {} if body is None else {"json": body}
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        **kwargs,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "waiting_approval"


# ── 7/8. 응답 안전성: 민감값 / 파일명 / 경로 미노출 ─────────────────────


def test_response_shape_is_minimal(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "check"},
    )
    data = r.json()
    # 정의된 응답 필드만 존재해야 한다
    assert set(data.keys()) == _RESPONSE_FIELDS


def test_response_has_no_approval_token_or_secrets(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    raw = r.text
    data = r.json()
    # 금지 필드가 응답에 없다
    for forbidden_key in (
        "token_id",
        "device_token",
        "token_hash",
        "approval_token",
        "screenshot_file",
        "screenshot_path",
        "path",
        "dir",
        "password",
        "secret",
        "cookie",
    ):
        assert forbidden_key not in data, f"{forbidden_key} must not appear"
        # 값 자체가 문자열로도 노출되면 안 됨 — raw 본문에서 필드명 자체 금지
        assert f'"{forbidden_key}"' not in raw


def test_response_has_no_full_path_or_image_filename(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False, "reason": "test"},
    )
    raw = r.text
    # 이미지 파일명 패턴 / 전체 경로 흔적이 응답에 존재하면 안 된다
    assert ".png" not in raw
    assert "screenshot_" not in raw
    assert "C:\\" not in raw
    assert "C:/" not in raw
    assert "/home/" not in raw
    assert ".haehan_agent" not in raw


# ── 9/10. 감사 로그 이벤트 ─────────────────────────────────────────────


def test_audit_emits_request_created_event(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True, "reason": "monthly"},
    )
    events = _audit_events()
    assert "CAPTURE_SCREENSHOT_REQUEST_CREATED" in events


def test_audit_still_emits_approval_requested(admin_user):
    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    events = _audit_events()
    # 기존 단계 이벤트 2 종이 여전히 남아야 한다
    assert "CAPTURE_SCREENSHOT_APPROVAL_REQUESTED" in events
    assert "LOCAL_AGENT_TASK_WAITING_APPROVAL" in events


def test_audit_log_does_not_leak_path_or_filename(admin_user):
    import ai_orchestrator.audit.audit_logger as _al

    client = _make_test_client(admin_user)
    agent_id, _ = _register(client)
    client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False, "reason": "ops"},
    )
    raw = _al._LOG_PATH.read_text(encoding="utf-8")
    # 경로 / 파일명 흔적은 본 엔드포인트가 남기지 않는다
    assert ".png" not in raw
    assert "C:\\" not in raw
    assert "C:/Users" not in raw
    assert ".haehan_agent" not in raw


# ── 11. 승인 전 WebSocket queued 미포함 ────────────────────────────────


def test_unapproved_request_not_in_ws_pending_list(admin_user):
    import ai_orchestrator.agent_hub.registry.facade as _reg

    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    task_id = r.json()["task_id"]

    # pending 큐(queued 상태만 포함)에 없어야 한다
    pending_ids = [t.task_id for t in _reg.list_pending_for_agent(agent_id)]
    assert task_id not in pending_ids

    # WS 로 접속해도 push 되지 않는다 (heartbeat_ack 만 수신)
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        ws.send_json({"type": "heartbeat"})
        assert ws.receive_json()["type"] == "heartbeat_ack"


# ── 권한 검사 ──────────────────────────────────────────────────────────


def test_viewer_cannot_create_request(admin_user, viewer_user):
    # 먼저 admin 으로 agent 등록
    admin_client = _make_test_client(admin_user)
    agent_id, _ = _register(admin_client)
    # viewer 는 403
    viewer_client = _make_test_client(viewer_user)
    r = viewer_client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
    )
    assert r.status_code == 403


def test_unknown_agent_returns_404(admin_user):
    client = _make_test_client(admin_user)
    r = client.post(
        "/api/v1/local-agents/la-nonexistent/capture-screenshot",
        json={"dry_run": True},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "AGENT_NOT_FOUND"


# ── dry_run=false + 승인까지 연결되는 end-to-end 회귀 ──────────────────


def test_explicit_real_request_then_approve_then_dispatch(admin_user):
    """dry_run=false 로 생성 → 기존 승인/WS push 흐름 유지 확인."""
    client = _make_test_client(admin_user)
    agent_id, token = _register(client)
    create = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": False},
    ).json()
    task_id = create["task_id"]

    # token_id 는 응답에 없으니 GET 으로 조회해 승인 수행
    fetched = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}").json()
    token_id = fetched["token_id"]
    assert token_id

    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": token_id},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "queued"

    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json({"type": "auth", "agent_id": agent_id, "device_token": token})
        assert ws.receive_json()["type"] == "auth_ok"
        msg = ws.receive_json()
        assert msg["type"] == "task"
        assert msg["task"]["action"] == "capture_screenshot"
        assert msg["task"]["approved"] is True
        assert msg["task"]["params"]["options"]["dry_run"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
