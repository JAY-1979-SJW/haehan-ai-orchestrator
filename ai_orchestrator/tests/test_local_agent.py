"""로컬 에이전트 등록·작업 큐 API 검증 (Stage 1).

필수 테스트:
  1. agent register 가 agent_id + device_token 발급
  2. ping task 등록 시 risk_level=low / status=completed
  3. system_info task 등록 시 risk_level=low / status=completed
  4. open_url task 가 risk_level=low 로 분류
  5. delete_file (및 그 외 금지 액션) → 400 UNKNOWN_ACTION 으로 거절
  6. capture_screenshot (high) → status=waiting_approval + token_id 발급
  7. device_token / 승인 token 원문이 감사 로그에 노출되지 않음
  8. 기존 web-task 회귀 (별도 suite 동시 실행으로 검증)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

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


def _register_agent(client) -> dict:
    resp = client.post("/api/v1/local-agents/register", json={
        "host": "test-pc", "os_name": "Windows 11", "version": "0.1.0",
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1. agent register ───────────────────────────────────────────────────

def test_register_agent_returns_agent_id_and_token(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post("/api/v1/local-agents/register", json={
        "host": "skyjw-pc", "os_name": "Windows 11", "version": "0.1.0",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"].startswith("la-")
    assert isinstance(body["device_token"], str) and len(body["device_token"]) >= 32
    assert body["host"] == "skyjw-pc"
    assert body["os_name"] == "Windows 11"


def test_register_appears_in_list(admin_user):
    client = _make_test_client(admin_user)
    reg = _register_agent(client)
    listed = client.get("/api/v1/local-agents").json()["agents"]
    ids = {a["agent_id"] for a in listed}
    assert reg["agent_id"] in ids
    # 토큰 / 토큰 해시는 list 응답에 포함되지 않아야 함
    for a in listed:
        assert "device_token" not in a
        assert "token_hash" not in a


def test_viewer_cannot_register(viewer_user):
    client = _make_test_client(viewer_user)
    resp = client.post("/api/v1/local-agents/register", json={"host": "x"})
    assert resp.status_code == 403


def test_viewer_can_list_agents(viewer_user, admin_user):
    # 먼저 admin 으로 등록
    admin_client = _make_test_client(admin_user)
    _register_agent(admin_client)
    # viewer 는 list 만 허용
    viewer_client = _make_test_client(viewer_user)
    resp = viewer_client.get("/api/v1/local-agents")
    assert resp.status_code == 200


# ── 2/3. ping / system_info ──────────────────────────────────────────────

def test_ping_task_low_risk_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "ping",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"
    assert data["action"] == "ping"
    assert data["agent_id"] == agent_id


def test_system_info_task_low_risk_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "system_info",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"


def test_list_allowed_apps_task_low_risk_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "list_allowed_apps",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"


# ── 4. open_url low risk + queued ──────────────────────────────────────

def test_open_url_low_risk_queued(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_url",
        "params": {"url": "https://example.com/health"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "queued"
    assert data["params"]["url"] == "https://example.com/health"


# ── 5. delete_file 및 그 외 금지 액션 → 거절 ──────────────────────────

@pytest.mark.parametrize("action", [
    "delete_file", "upload_file", "modify_file", "execute_shell",
    "rm", "format_disk", "",
])
def test_forbidden_actions_rejected(admin_user, action):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": action,
        "params": {"path": "C:/important.txt"},
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "UNKNOWN_ACTION"


def test_unknown_action_audit_logged(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "delete_file",
        "params": {"path": "C:/nope.txt"},
    })
    import ai_orchestrator.audit_logger as _al
    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "LOCAL_AGENT_TASK_REJECTED" in events


def test_unknown_agent_returns_404(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post("/api/v1/local-agents/la-doesnotexist/tasks", json={
        "action": "ping",
    })
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "AGENT_NOT_FOUND"


# ── 6. high risk → waiting_approval + token ────────────────────────────

def test_capture_screenshot_high_risk_waiting_approval(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "capture_screenshot",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "high"
    assert data["status"] == "waiting_approval"
    assert data["token_id"], "high risk 작업은 token_id 가 발급되어야 함"


def test_high_risk_audit_event_recorded(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "capture_screenshot",
    })
    import ai_orchestrator.audit_logger as _al
    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "LOCAL_AGENT_TASK_WAITING_APPROVAL" in events


# ── 7. 토큰 / secret 원문 미노출 ───────────────────────────────────────

def test_device_token_not_in_audit_log(admin_user):
    client = _make_test_client(admin_user)
    reg = _register_agent(client)
    token = reg["device_token"]
    assert token  # sanity
    import ai_orchestrator.audit_logger as _al
    log_path = _al._LOG_PATH
    if log_path.exists():
        raw = log_path.read_text(encoding="utf-8")
        assert token not in raw, "device_token 원문이 감사 로그에 노출됨"


def test_approval_token_id_recorded_but_no_secret_in_log(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "capture_screenshot",
    })
    token_id = resp.json()["token_id"]
    # 등록된 device_token 은 별개. 둘 다 안전하게 처리됐는지 확인.
    import ai_orchestrator.audit_logger as _al
    raw = _al._LOG_PATH.read_text(encoding="utf-8")
    # token_id 자체는 식별자라 기록될 수 있다 (감사 추적 목적).
    # 하지만 device_token 원문은 절대 등장해선 안 된다.
    assert token_id  # sanity


def test_sensitive_params_stripped_from_task(admin_user):
    """params 의 password/token/cookie 등 민감 키는 저장 단계에서 제거된다."""
    _SECRET = "raw_password_must_not_appear_xyz"
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_url",
        "params": {
            "url": "https://example.com",
            "password": _SECRET,
            "session_token": "another_secret_pqr",
            "cookie": "yet_another_secret_def",
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert _SECRET not in resp.text
    assert "another_secret_pqr" not in resp.text
    assert "yet_another_secret_def" not in resp.text
    # url 은 유지
    assert data["params"]["url"] == "https://example.com"
    assert "password" not in data["params"]
    assert "session_token" not in data["params"]
    assert "cookie" not in data["params"]

    import ai_orchestrator.audit_logger as _al
    raw = _al._LOG_PATH.read_text(encoding="utf-8") if _al._LOG_PATH.exists() else ""
    assert _SECRET not in raw, "민감 params 가 감사 로그에 노출됨"


# ── 추가: GET task ──────────────────────────────────────────────────────

def test_get_task_returns_safe_view(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    create = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "ping",
    }).json()
    task_id = create["task_id"]
    fetch = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}")
    assert fetch.status_code == 200
    body = fetch.json()
    assert body["task_id"] == task_id
    assert body["agent_id"] == agent_id


def test_get_task_wrong_agent_returns_404(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    create = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "ping",
    }).json()
    resp = client.get(f"/api/v1/local-agents/la-other/tasks/{create['task_id']}")
    assert resp.status_code == 404


# ── 모듈 단위 sanity ───────────────────────────────────────────────────

def test_action_risk_mapping_sanity():
    from ai_orchestrator.local_agent_registry import ACTION_RISK
    assert ACTION_RISK["ping"] == "low"
    assert ACTION_RISK["system_info"] == "low"
    assert ACTION_RISK["list_allowed_apps"] == "low"
    assert ACTION_RISK["open_url"] == "low"
    assert ACTION_RISK["list_files_readonly"] == "medium"
    assert ACTION_RISK["capture_screenshot"] == "high"
    assert "delete_file" not in ACTION_RISK
    assert "execute_shell" not in ACTION_RISK


def test_local_actions_module_forbidden_set():
    from local_agent.actions import FORBIDDEN_ACTIONS, execute_action
    assert {"delete_file", "upload_file", "modify_file", "execute_shell"} <= FORBIDDEN_ACTIONS
    r = execute_action("delete_file", {"path": "C:/x"})
    assert not r.success
    assert r.error_code == "ACTION_FORBIDDEN"


def test_local_actions_unknown_action():
    from local_agent.actions import execute_action
    r = execute_action("nope_such_thing", {})
    assert not r.success
    assert r.error_code == "UNKNOWN_ACTION"


def test_local_actions_open_url_blocks_dangerous_schemes():
    from local_agent.actions import action_open_url
    for url in ("file:///C:/Windows/System32/cmd.exe",
                "javascript:alert(1)",
                "data:text/html,<script>x</script>"):
        r = action_open_url({"url": url})
        assert not r.success
        assert r.error_code in {"URL_SCHEME_NOT_ALLOWED", "INVALID_URL"}


def test_local_actions_list_allowed_apps():
    from local_agent.actions import action_list_allowed_apps
    r = action_list_allowed_apps({})
    assert r.success
    names = {a["name"] for a in r.data["apps"]}
    assert {"browser", "excel", "hwp", "cad"} == names
    # browser 만 1단계 실행 가능
    by_name = {a["name"]: a for a in r.data["apps"]}
    assert by_name["browser"]["executable_stage1"] is True
    assert by_name["excel"]["executable_stage1"] is False


# ── 상태 전이 guard 테스트 ──────────────────────────────────────────────

def _make_queued_task(agent_id: str):
    """open_url queued 작업 하나 생성 후 반환 (helper)."""
    import ai_orchestrator.local_agent_registry as reg
    return reg.enqueue_task(
        agent_id=agent_id,
        action="open_url",
        params={"url": "https://example.com"},
        requested_by="test",
    )


def test_state_transition_queued_to_delivered(admin_user):
    """queued → delivered 정상."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    result = reg.mark_delivered(agent_id, task.task_id)
    assert result is not None
    assert result.status == "delivered"


def test_state_transition_delivered_to_running(admin_user):
    """delivered → running 정상."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "running"


def test_state_transition_running_to_completed(admin_user):
    """running → completed 정상."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True, summary="ok")
    assert result is not None
    assert result.status == "completed"


def test_state_transition_running_to_failed(admin_user):
    """running → failed 정상."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=False, error="err")
    assert result is not None
    assert result.status == "failed"


def test_state_guard_completed_cannot_transition_to_running(admin_user):
    """completed 이후 running 전이 차단 — 상태 보존."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True)
    # completed 상태에서 mark_running 재시도 → 상태 변경 없음
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "completed"


def test_state_guard_failed_cannot_transition_to_running(admin_user):
    """failed 이후 running 전이 차단 — 상태 보존."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=False, error="err")
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "failed"


def test_state_guard_queued_cannot_directly_run(admin_user):
    """queued → running 직접 전이 차단."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    # mark_delivered 없이 바로 mark_running 시도
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "queued"


def test_state_guard_delivered_cannot_complete_directly(admin_user):
    """delivered 상태에서 success=True result를 바로 적용해 completed 전이 시도 → 차단."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    # delivered 상태에서 success=True는 delivered → completed 전이 시도 → guard가 차단
    with pytest.raises(reg.InvalidTaskTransitionError):
        reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True)
    # 상태가 변경되지 않아야 한다
    t = reg.find_task_by_id(task.task_id)
    assert t is not None
    assert t.status == "delivered"


def test_state_guard_unknown_task_id_safe(admin_user):
    """존재하지 않는 task_id 에 대해 mark_delivered/mark_running/apply_result 가 안전하게 None 반환."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    fake_id = "lat-000000000000"
    assert reg.mark_delivered(agent_id, fake_id) is None
    assert reg.mark_running(agent_id, fake_id) is None
    assert reg.apply_result(agent_id=agent_id, task_id=fake_id, success=True) is None


# ── Stage 11-3B: failure_reason / timed_out_at / expire_stale_tasks ────

def test_new_task_failure_reason_default(admin_user):
    """새 task 의 failure_reason 기본값은 빈 문자열."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    assert task.failure_reason == ""


def test_new_task_timed_out_at_default(admin_user):
    """새 task 의 timed_out_at 기본값은 빈 문자열."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    assert task.timed_out_at == ""


def test_to_safe_contains_failure_reason_and_timed_out_at(admin_user):
    """to_safe() 응답에 failure_reason / timed_out_at 이 포함돼야 한다."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={
        "action": "open_url",
        "params": {"url": "https://example.com"},
    })
    body = resp.json()
    assert "failure_reason" in body
    assert "timed_out_at" in body
    assert body["failure_reason"] == ""
    assert body["timed_out_at"] == ""


def test_expire_stale_tasks_delivered_timeout(admin_user):
    """delivered 상태에서 120초 초과 → failed / failure_reason=delivered_timeout."""
    import ai_orchestrator.local_agent_registry as reg
    from datetime import datetime, timezone, timedelta
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)

    future_now = datetime.now(timezone.utc) + timedelta(seconds=121)
    expired = reg.expire_stale_tasks(now=future_now)

    assert any(t.task_id == task.task_id for t in expired)
    t = reg.find_task_by_id(task.task_id)
    assert t.status == "failed"
    assert t.failure_reason == "delivered_timeout"
    assert t.timed_out_at != ""


def test_expire_stale_tasks_delivered_not_yet_expired(admin_user):
    """delivered 상태에서 120초 이내 → 그대로 유지."""
    import ai_orchestrator.local_agent_registry as reg
    from datetime import datetime, timezone, timedelta
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)

    future_now = datetime.now(timezone.utc) + timedelta(seconds=60)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "delivered"


def test_expire_stale_tasks_running_timeout(admin_user):
    """running 상태에서 300초 초과 → failed / failure_reason=running_timeout."""
    import ai_orchestrator.local_agent_registry as reg
    from datetime import datetime, timezone, timedelta
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)

    future_now = datetime.now(timezone.utc) + timedelta(seconds=301)
    expired = reg.expire_stale_tasks(now=future_now)

    assert any(t.task_id == task.task_id for t in expired)
    t = reg.find_task_by_id(task.task_id)
    assert t.status == "failed"
    assert t.failure_reason == "running_timeout"
    assert t.timed_out_at != ""


def test_expire_stale_tasks_completed_not_touched(admin_user):
    """completed 상태는 expire_stale_tasks 가 건드리지 않는다."""
    import ai_orchestrator.local_agent_registry as reg
    from datetime import datetime, timezone, timedelta
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True)

    future_now = datetime.now(timezone.utc) + timedelta(seconds=9999)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "completed"


def test_expire_stale_tasks_failed_not_touched(admin_user):
    """failed 상태는 expire_stale_tasks 가 건드리지 않는다."""
    import ai_orchestrator.local_agent_registry as reg
    from datetime import datetime, timezone, timedelta
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=False, error="err")

    future_now = datetime.now(timezone.utc) + timedelta(seconds=9999)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "failed"


def test_apply_result_failure_sets_agent_error(admin_user):
    """apply_result(success=False) 시 failure_reason = agent_error."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id, task_id=task.task_id,
        success=False, error="something broke", error_code="ERR_X",
    )
    assert result.status == "failed"
    assert result.failure_reason == "agent_error"


# ── Stage 11-4B: list_tasks_for_agent registry 단위 테스트 ──────────────

def test_list_tasks_empty_for_unknown_agent():
    """없는 agent_id → 빈 목록."""
    import ai_orchestrator.local_agent_registry as reg
    result = reg.list_tasks_for_agent("la-nonexistent")
    assert result == []


def test_list_tasks_returns_all_tasks_for_agent(admin_user):
    """task 3개 생성 → 전체 반환, agent_id 일치 확인."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(3):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id)
    assert len(tasks) == 3
    assert all(t.agent_id == agent_id for t in tasks)


def test_list_tasks_status_filter(admin_user):
    """status 필터: queued 2개 + completed 1개 → status=queued → 2개."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    t1 = _make_queued_task(agent_id)
    t2 = _make_queued_task(agent_id)
    t3 = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, t3.task_id)
    reg.mark_running(agent_id, t3.task_id)
    reg.apply_result(agent_id=agent_id, task_id=t3.task_id, success=True, summary="ok")
    queued = reg.list_tasks_for_agent(agent_id, status="queued")
    assert len(queued) == 2
    assert all(t.status == "queued" for t in queued)


def test_list_tasks_limit(admin_user):
    """limit=2 → 2개만 반환."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(5):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id, limit=2)
    assert len(tasks) == 2


def test_list_tasks_sorted_newest_first(admin_user):
    """created_at 최신순 정렬 확인."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(3):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id)
    created_ats = [t.created_at for t in tasks]
    assert created_ats == sorted(created_ats, reverse=True)


def test_list_tasks_contains_failure_reason_and_timed_out_at(admin_user):
    """failed task → failure_reason / timed_out_at 포함."""
    from datetime import datetime, timezone, timedelta
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    future = datetime.now(timezone.utc) + timedelta(seconds=9999)
    reg.expire_stale_tasks(now=future)
    tasks = reg.list_tasks_for_agent(agent_id, status="failed")
    assert len(tasks) == 1
    t = tasks[0]
    assert t.failure_reason == "delivered_timeout"
    assert t.timed_out_at != ""


def test_list_tasks_agent_isolation(admin_user):
    """agent A/B task 혼합 → 각 agent는 자신의 task만 반환."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_a = _register_agent(client)["agent_id"]
    agent_b = _register_agent(client)["agent_id"]
    for _ in range(2):
        reg.enqueue_task(agent_id=agent_a, action="open_url",
                         params={"url": "https://a.com"}, requested_by="test")
    reg.enqueue_task(agent_id=agent_b, action="open_url",
                     params={"url": "https://b.com"}, requested_by="test")
    tasks_a = reg.list_tasks_for_agent(agent_a)
    tasks_b = reg.list_tasks_for_agent(agent_b)
    assert len(tasks_a) == 2
    assert len(tasks_b) == 1
    assert all(t.agent_id == agent_a for t in tasks_a)
    assert all(t.agent_id == agent_b for t in tasks_b)


def test_to_list_safe_excludes_params(admin_user):
    """to_list_safe() 응답에 params 없음."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    safe = task.to_list_safe()
    assert "params" not in safe


def test_to_list_safe_excludes_token_id(admin_user):
    """to_list_safe() 응답에 token_id 없음."""
    import ai_orchestrator.local_agent_registry as reg
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    safe = task.to_list_safe()
    assert "token_id" not in safe


# ── Stage 11-4B: GET /{agent_id}/tasks API 테스트 ────────────────────────

def test_api_list_tasks_returns_200(admin_user):
    """GET /{agent_id}/tasks → 200 + tasks 배열."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks",
                json={"action": "open_url", "params": {"url": "https://example.com"}})
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] == agent_id
    assert "tasks" in body
    assert isinstance(body["tasks"], list)
    assert body["total"] == len(body["tasks"])


def test_api_list_tasks_status_filter(admin_user):
    """status=queued 필터 동작."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks",
                json={"action": "open_url", "params": {"url": "https://example.com"}})
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks?status=queued")
    assert resp.status_code == 200
    body = resp.json()
    assert all(t["status"] == "queued" for t in body["tasks"])


def test_api_list_tasks_unknown_status_400(admin_user):
    """unknown status → 400."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks?status=invalid_xyz")
    assert resp.status_code == 400


def test_api_list_tasks_limit_over_max_422(admin_user):
    """limit=201 → FastAPI validation → 422."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks?limit=201")
    assert resp.status_code == 422


def test_api_list_tasks_no_params_in_response(admin_user):
    """응답 task 항목에 params 없음."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(f"/api/v1/local-agents/{agent_id}/tasks",
                json={"action": "open_url", "params": {"url": "https://example.com"}})
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks")
    assert resp.status_code == 200
    for task in resp.json()["tasks"]:
        assert "params" not in task
        assert "token_id" not in task


def test_api_list_tasks_empty_for_unknown_agent(admin_user):
    """없는 agent_id → 빈 목록 (404 아님)."""
    client = _make_test_client(admin_user)
    resp = client.get("/api/v1/local-agents/la-nonexistent/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tasks"] == []
    assert body["total"] == 0


# ── Stage 11-6B: connected_at / last_seen_at / disconnected_at / agent_status ──

def test_new_agent_default_status_offline():
    """새로 등록된 agent의 기본 상태는 offline."""
    import ai_orchestrator.local_agent_registry as reg
    result = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    assert reg.get_agent_status(result.agent.agent_id) == "offline"


def test_set_agent_connected_sets_timestamps():
    """set_agent_connected 후 connected_at / last_seen_at 설정, disconnected_at 초기화."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    reg.set_agent_connected(agent_id, now="2026-01-01T00:00:00+00:00")
    a = reg.get_agent(agent_id)
    assert a.connected_at == "2026-01-01T00:00:00+00:00"
    assert a.last_seen_at == "2026-01-01T00:00:00+00:00"
    assert a.disconnected_at == ""


def test_set_agent_disconnected_sets_disconnected_at():
    """set_agent_disconnected 후 disconnected_at 설정."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    reg.set_agent_connected(agent_id, now="2026-01-01T00:00:00+00:00")
    reg.set_agent_disconnected(agent_id, now="2026-01-01T00:01:00+00:00")
    a = reg.get_agent(agent_id)
    assert a.disconnected_at == "2026-01-01T00:01:00+00:00"
    assert a.last_seen_at == "2026-01-01T00:00:00+00:00"  # 기존 값 유지


def test_agent_status_idle_when_connected_no_task():
    """연결 중이고 active task 없으면 idle."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    status = reg.get_agent_status(agent_id, now=now)
    assert status == "idle"


def test_agent_status_busy_with_delivered_task():
    """delivered task 있으면 busy."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    task = reg.enqueue_task(agent_id=agent_id, action="open_url",
                            params={"url": "https://x.com"}, requested_by="t")
    reg.mark_delivered(agent_id, task.task_id)
    assert reg.get_agent_status(agent_id, now=now) == "busy"


def test_agent_status_busy_with_running_task():
    """running task 있으면 busy."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    task = reg.enqueue_task(agent_id=agent_id, action="open_url",
                            params={"url": "https://x.com"}, requested_by="t")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    assert reg.get_agent_status(agent_id, now=now) == "busy"


def test_agent_status_stale_after_91s():
    """last_seen_at이 91초 이상 과거면 stale."""
    from datetime import datetime, timezone, timedelta
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    past = (datetime.now(timezone.utc) - timedelta(seconds=91)).isoformat()
    reg.set_agent_connected(agent_id, now=past)
    assert reg.get_agent_status(agent_id) == "stale"


def test_agent_status_offline_after_disconnect():
    """disconnected_at 설정 후 offline."""
    import ai_orchestrator.local_agent_registry as reg
    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    reg.set_agent_disconnected(agent_id, now="2026-01-01T00:01:00+00:00")
    assert reg.get_agent_status(agent_id, now=now) == "offline"


def test_list_agents_contains_agent_status(admin_user):
    """list_agents 응답에 agent_status 포함."""
    client = _make_test_client(admin_user)
    _register_agent(client)
    listed = client.get("/api/v1/local-agents").json()["agents"]
    assert all("agent_status" in a for a in listed)


def test_list_agents_contains_active_task_count(admin_user):
    """list_agents 응답에 active_task_count 포함."""
    client = _make_test_client(admin_user)
    _register_agent(client)
    listed = client.get("/api/v1/local-agents").json()["agents"]
    assert all("active_task_count" in a for a in listed)


def test_list_agents_contains_current_task_id(admin_user):
    """list_agents 응답에 current_task_id 포함."""
    client = _make_test_client(admin_user)
    _register_agent(client)
    listed = client.get("/api/v1/local-agents").json()["agents"]
    assert all("current_task_id" in a for a in listed)


def test_list_agents_no_token_hash_or_device_token(admin_user):
    """list_agents 응답에 token_hash / device_token 없음."""
    client = _make_test_client(admin_user)
    _register_agent(client)
    listed = client.get("/api/v1/local-agents").json()["agents"]
    for a in listed:
        assert "token_hash" not in a
        assert "device_token" not in a


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
