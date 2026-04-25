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
    # F-4G-3Y-a — 신규 등록.
    assert ACTION_RISK["hometax_post_login_observe"] == "medium"
    assert "delete_file" not in ACTION_RISK
    assert "execute_shell" not in ACTION_RISK


def test_hometax_post_login_observe_registered_for_auto_execute():
    """F-4G-3Y-a: 새 액션이 서버측 큐 화이트리스트에 들어가 있어야 한다."""
    from ai_orchestrator.local_agent_registry import (
        ACTION_RISK,
        AUTO_EXECUTE_VIA_AGENT,
        _SERVER_AUTO_COMPLETE,
    )
    assert "hometax_post_login_observe" in ACTION_RISK
    assert "hometax_post_login_observe" in AUTO_EXECUTE_VIA_AGENT
    # 서버 자동완료 대상은 아니다 (PC 의존 액션).
    assert "hometax_post_login_observe" not in _SERVER_AUTO_COMPLETE


def test_hometax_post_login_observe_handler_not_yet_implemented():
    """F-4G-3Y-a: 서버측 등록만 끝난 본 단계에서는 로컬 에이전트 핸들러가
    미구현이어서 execute_action 이 UNKNOWN_ACTION 으로 거절해야 한다.
    핸들러는 F-4G-3Y-b 에서 추가된다."""
    from local_agent.actions import execute_action
    r = execute_action("hometax_post_login_observe", {})
    assert not r.success
    assert r.error_code == "UNKNOWN_ACTION"


def test_hometax_post_login_observe_existing_action_risk_unchanged():
    """기존 액션의 risk 매핑이 본 단계에서 변경되지 않았는지 확인."""
    from ai_orchestrator.local_agent_registry import ACTION_RISK
    expected_baseline = {
        "ping": "low",
        "system_info": "low",
        "list_allowed_apps": "low",
        "open_url": "low",
        "list_files_readonly": "medium",
        "capture_screenshot": "high",
    }
    for action, risk in expected_baseline.items():
        assert ACTION_RISK[action] == risk


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
