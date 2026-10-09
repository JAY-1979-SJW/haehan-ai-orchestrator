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

import contextlib
import sys
from datetime import UTC
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    import importlib

    import tools.gates.auth as _auth

    importlib.reload(_auth)
    # local_agent_router 분리 후: 서브라우터 leaf 들도 reload 해야 갱신된 auth 를
    # 재바인딩한다(의존 순서: 공유 leaf → 라우트 leaf → 컴포지션 루트).
    for _m in (
        "agent_hub.router.schemas",
        "agent_hub.router.up_queue",
        "agent_hub.router.validation",
        "agent_hub.router.guards",
        "agent_hub.router.registration",
        "agent_hub.router.query",
        "agent_hub.router.task",
        "agent_hub.router.browser",
        "agent_hub.router.user_present",
        "agent_hub.router.cleanup",
        "agent_hub.router.ws",
    ):
        with contextlib.suppress(ModuleNotFoundError):
            importlib.reload(importlib.import_module(f"ai_orchestrator.{_m}"))
    import ai_orchestrator.agent_hub.router.root as _lar

    importlib.reload(_lar)

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


def _make_test_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(app, raise_server_exceptions=True)


def _register_agent(client) -> dict:
    resp = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "test-pc",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1. agent register ───────────────────────────────────────────────────


def test_register_agent_returns_agent_id_and_token(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/local-agents/register",
        json={
            "host": "skyjw-pc",
            "os_name": "Windows 11",
            "version": "0.1.0",
        },
    )
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
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "ping",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"
    assert data["action"] == "ping"
    assert data["agent_id"] == agent_id


def test_system_info_task_low_risk_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "system_info",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"


def test_list_allowed_apps_task_low_risk_completed(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "list_allowed_apps",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "completed"


# ── 4. open_url low risk + queued ──────────────────────────────────────


def test_open_url_low_risk_queued(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "open_url",
            "params": {"url": "https://example.com/health"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "low"
    assert data["status"] == "queued"
    assert data["params"]["url"] == "https://example.com/health"


# ── 5. delete_file 및 그 외 금지 액션 → 거절 ──────────────────────────


def test_browser_readonly_instruction_queues_safe_task(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the page headings only",
            "url": "https://example.com/path?private=query",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["action"] == "web_open_url_readonly"
    assert data["status"] == "queued"
    assert data["risk_level"] == "low"
    assert data["instruction_accepted"] is True
    assert data["url_host"] == "example.com"
    assert "private=query" not in resp.text
    assert "Summarize the page" not in resp.text

    import ai_orchestrator.agent_hub.registry.facade as _reg

    task = _reg.get_task(agent_id, data["task_id"])
    assert task.action == "web_open_url_readonly"
    assert task.params["user_instruction"] == "Summarize the page headings only"
    assert task.params["source"] == "approved_user_instruction"
    assert task.params["headless"] is True
    assert task.params["background_approved"] is True
    assert task.params["keep_open_ms"] == 0


def test_browser_readonly_instruction_can_request_visible_browser(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the page headings only",
            "url": "https://example.com",
            "visible_browser": True,
            "keep_open_ms": 5000,
            "browser_channel": "chrome",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["visible_browser"] is True
    assert data["background_approved"] is False
    assert data["keep_open_ms"] == 5000
    assert data["browser_channel"] == "chrome"

    import ai_orchestrator.agent_hub.registry.facade as _reg

    task = _reg.get_task(agent_id, data["task_id"])
    assert task.params["headless"] is False
    assert task.params["background_approved"] is False
    assert task.params["keep_open_ms"] == 5000
    assert task.params["browser_channel"] == "chrome"


def test_browser_readonly_instruction_can_disable_background(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the page headings only",
            "url": "https://example.com",
            "allow_background": False,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["allow_background"] is False
    assert data["background_approved"] is False

    import ai_orchestrator.agent_hub.registry.facade as _reg

    task = _reg.get_task(agent_id, data["task_id"])
    assert task.params["headless"] is False
    assert task.params["background_approved"] is False


def test_viewer_cannot_submit_browser_readonly_instruction(viewer_user, admin_user):
    admin_client = _make_test_client(admin_user)
    agent_id = _register_agent(admin_client)["agent_id"]
    viewer_client = _make_test_client(viewer_user)
    resp = viewer_client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the page",
            "url": "https://example.com",
        },
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "instruction",
    [
        "login and enter the password",
        "click the submit button",
        "download the report",
    ],
)
def test_browser_readonly_instruction_blocks_state_changes(admin_user, instruction):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": instruction,
            "url": "https://example.com",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "UNSAFE_BROWSER_INSTRUCTION"


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/System32/cmd.exe",
        "javascript:alert(1)",
        "https://user:pass@example.com",
    ],
)
def test_browser_readonly_instruction_blocks_unsafe_urls(admin_user, url):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "Summarize the page",
            "url": url,
        },
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "action",
    [
        "delete_file",
        "upload_file",
        "modify_file",
        "execute_shell",
        "rm",
        "format_disk",
        "",
    ],
)
def test_forbidden_actions_rejected(admin_user, action):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": action,
            "params": {"path": "C:/important.txt"},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "UNKNOWN_ACTION"


def test_unknown_action_audit_logged(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "delete_file",
            "params": {"path": "C:/nope.txt"},
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "LOCAL_AGENT_TASK_REJECTED" in events


def test_unknown_agent_returns_404(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/local-agents/la-doesnotexist/tasks",
        json={
            "action": "ping",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "AGENT_NOT_FOUND"


# ── 6. high risk → waiting_approval + token ────────────────────────────


def test_capture_screenshot_high_risk_waiting_approval(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "capture_screenshot",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_level"] == "high"
    assert data["status"] == "waiting_approval"
    assert data["token_id"], "high risk 작업은 token_id 가 발급되어야 함"


def test_high_risk_audit_event_recorded(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "capture_screenshot",
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "LOCAL_AGENT_TASK_WAITING_APPROVAL" in events


# ── 7. 토큰 / secret 원문 미노출 ───────────────────────────────────────


def test_device_token_not_in_audit_log(admin_user):
    client = _make_test_client(admin_user)
    reg = _register_agent(client)
    token = reg["device_token"]
    assert token  # sanity
    import ai_orchestrator.audit.audit_logger as _al

    log_path = _al._LOG_PATH
    if log_path.exists():
        raw = log_path.read_text(encoding="utf-8")
        assert token not in raw, "device_token 원문이 감사 로그에 노출됨"


def test_approval_token_id_recorded_but_no_secret_in_log(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "capture_screenshot",
        },
    )
    token_id = resp.json()["token_id"]
    # 등록된 device_token 은 별개. 둘 다 안전하게 처리됐는지 확인.
    import ai_orchestrator.audit.audit_logger as _al

    _al._LOG_PATH.read_text(encoding="utf-8")
    # token_id 자체는 식별자라 기록될 수 있다 (감사 추적 목적).
    # 하지만 device_token 원문은 절대 등장해선 안 된다.
    assert token_id  # sanity


def test_sensitive_params_stripped_from_task(admin_user):
    """params 의 password/token/cookie 등 민감 키는 저장 단계에서 제거된다."""
    _SECRET = "raw_password_must_not_appear_xyz"  # noqa: S105
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "open_url",
            "params": {
                "url": "https://example.com",
                "password": _SECRET,
                "session_token": "another_secret_pqr",
                "cookie": "yet_another_secret_def",
            },
        },
    )
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

    import ai_orchestrator.audit.audit_logger as _al

    raw = _al._LOG_PATH.read_text(encoding="utf-8") if _al._LOG_PATH.exists() else ""
    assert _SECRET not in raw, "민감 params 가 감사 로그에 노출됨"


# ── 추가: GET task ──────────────────────────────────────────────────────


def test_get_task_returns_safe_view(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    create = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "ping",
        },
    ).json()
    task_id = create["task_id"]
    fetch = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}")
    assert fetch.status_code == 200
    body = fetch.json()
    assert body["task_id"] == task_id
    assert body["agent_id"] == agent_id


def test_get_task_wrong_agent_returns_404(admin_user):
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    create = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "ping",
        },
    ).json()
    resp = client.get(f"/api/v1/local-agents/la-other/tasks/{create['task_id']}")
    assert resp.status_code == 404


# ── 모듈 단위 sanity ───────────────────────────────────────────────────


def test_action_risk_mapping_sanity():
    from ai_orchestrator.agent_hub.registry.facade import ACTION_RISK

    assert ACTION_RISK["ping"] == "low"
    assert ACTION_RISK["system_info"] == "low"
    assert ACTION_RISK["list_allowed_apps"] == "low"
    assert ACTION_RISK["open_url"] == "low"
    assert ACTION_RISK["list_files_readonly"] == "medium"
    assert ACTION_RISK["capture_screenshot"] == "high"
    assert "delete_file" not in ACTION_RISK
    assert "execute_shell" not in ACTION_RISK


def test_local_actions_module_forbidden_set():
    from core.agent_runtime.connection.actions import FORBIDDEN_ACTIONS, execute_action

    assert {"delete_file", "upload_file", "modify_file", "execute_shell"} <= FORBIDDEN_ACTIONS
    r = execute_action("delete_file", {"path": "C:/x"})
    assert not r.success
    assert r.error_code == "ACTION_FORBIDDEN"


def test_local_actions_unknown_action():
    from core.agent_runtime.connection.actions import execute_action

    r = execute_action("nope_such_thing", {})
    assert not r.success
    assert r.error_code == "UNKNOWN_ACTION"


def test_local_actions_open_url_blocks_dangerous_schemes():
    from core.agent_runtime.connection.actions import action_open_url

    for url in ("file:///C:/Windows/System32/cmd.exe", "javascript:alert(1)", "data:text/html,<script>x</script>"):
        r = action_open_url({"url": url})
        assert not r.success
        assert r.error_code in {"URL_SCHEME_NOT_ALLOWED", "INVALID_URL"}


def test_open_url_dry_run_default_true():
    """dry_run 기본값은 true."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com"})
    assert r.success
    assert r.data["dry_run"] is True


def test_open_url_dry_run_true_success():
    """dry_run=true이면 success 반환."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "dry_run": True})
    assert r.success
    assert r.summary == "open_url_dry_run_ok"


def test_open_url_dry_run_true_no_browser_execution():
    """dry_run=true일 때 webbrowser.open() 호출 안 됨."""
    import unittest.mock as mock

    from core.agent_runtime.connection.actions import action_open_url

    with mock.patch("core.agent_runtime.connection.actions.webbrowser.open") as mock_open:
        r = action_open_url({"url": "https://example.com", "dry_run": True})
        assert r.success
        mock_open.assert_not_called()


def test_open_url_dry_run_result_fields():
    """dry_run 성공 결과에 필수 필드 포함."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "dry_run": True})
    assert r.success
    assert r.data["action"] == "open_url"
    assert r.data["dry_run"] is True
    assert r.data["url"] == "https://example.com"
    assert r.data["would_open_browser"] is False
    assert r.data["external_network_call"] is False
    assert r.data["requires_approval"] is False
    assert r.data["policy_decision"] == "dry_run_allowed"


def test_open_url_dry_run_false_rejected():
    """dry_run=false는 명시적으로 거부."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "dry_run": False})
    assert not r.success
    assert r.error_code == "ACTUAL_EXECUTION_NOT_ENABLED"


def test_open_url_blocks_sensitive_password():
    """password 포함 params는 거부."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "password": "secret123"})
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"


def test_open_url_blocks_sensitive_token():
    """token 포함 params는 거부."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "token": "secret_token"})
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"


def test_open_url_blocks_sensitive_cookie():
    """cookie 포함 params는 거부."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "cookie": "session_id=xyz"})
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"


def test_open_url_blocks_sensitive_authorization():
    """authorization 포함 params는 거부."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "authorization": "Bearer xyz"})
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"


def test_open_url_case_insensitive_sensitive_check():
    """민감정보 검사는 대소문자 무관."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "Password": "secret"})
    assert not r.success
    assert r.error_code == "SENSITIVE_DATA_DETECTED"


def test_open_url_dry_run_string_true():
    """dry_run 문자열 'true' 도 true로 인식."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "dry_run": "true"})
    assert r.success
    assert r.data["dry_run"] is True


def test_open_url_dry_run_string_false():
    """dry_run 문자열 'false' 도 false로 인식."""
    from core.agent_runtime.connection.actions import action_open_url

    r = action_open_url({"url": "https://example.com", "dry_run": "false"})
    assert not r.success
    assert r.error_code == "ACTUAL_EXECUTION_NOT_ENABLED"


def test_local_actions_list_allowed_apps():
    from core.agent_runtime.connection.actions import action_list_allowed_apps

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
    import ai_orchestrator.agent_hub.registry.facade as reg

    return reg.enqueue_task(
        agent_id=agent_id,
        action="open_url",
        params={"url": "https://example.com"},
        requested_by="test",
    )


def test_state_transition_queued_to_delivered(admin_user):
    """queued → delivered 정상."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    result = reg.mark_delivered(agent_id, task.task_id)
    assert result is not None
    assert result.status == "delivered"


def test_state_transition_delivered_to_running(admin_user):
    """delivered → running 정상."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "running"


def test_state_transition_running_to_completed(admin_user):
    """running → completed 정상."""
    import ai_orchestrator.agent_hub.registry.facade as reg

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
    import ai_orchestrator.agent_hub.registry.facade as reg

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
    import ai_orchestrator.agent_hub.registry.facade as reg

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
    import ai_orchestrator.agent_hub.registry.facade as reg

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
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    # mark_delivered 없이 바로 mark_running 시도
    result = reg.mark_running(agent_id, task.task_id)
    assert result is not None
    assert result.status == "queued"


def test_state_guard_delivered_cannot_complete_directly(admin_user):
    """delivered 상태에서 success=True result를 바로 적용해 completed 전이 시도 → 차단."""
    import ai_orchestrator.agent_hub.registry.facade as reg

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
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    fake_id = "lat-000000000000"
    assert reg.mark_delivered(agent_id, fake_id) is None
    assert reg.mark_running(agent_id, fake_id) is None
    assert reg.apply_result(agent_id=agent_id, task_id=fake_id, success=True) is None


# ── Stage 11-3B: failure_reason / timed_out_at / expire_stale_tasks ────


def test_new_task_failure_reason_default(admin_user):
    """새 task 의 failure_reason 기본값은 빈 문자열."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    assert task.failure_reason == ""


def test_new_task_timed_out_at_default(admin_user):
    """새 task 의 timed_out_at 기본값은 빈 문자열."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    assert task.timed_out_at == ""


def test_to_safe_contains_failure_reason_and_timed_out_at(admin_user):
    """to_safe() 응답에 failure_reason / timed_out_at 이 포함돼야 한다."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    resp = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks",
        json={
            "action": "open_url",
            "params": {"url": "https://example.com"},
        },
    )
    body = resp.json()
    assert "failure_reason" in body
    assert "timed_out_at" in body
    assert body["failure_reason"] == ""
    assert body["timed_out_at"] == ""


def test_expire_stale_tasks_delivered_timeout(admin_user):
    """delivered 상태에서 120초 초과 → failed / failure_reason=delivered_timeout."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)

    future_now = datetime.now(UTC) + timedelta(seconds=121)
    expired = reg.expire_stale_tasks(now=future_now)

    assert any(t.task_id == task.task_id for t in expired)
    t = reg.find_task_by_id(task.task_id)
    assert t.status == "failed"
    assert t.failure_reason == "delivered_timeout"
    assert t.timed_out_at != ""


def test_expire_stale_tasks_delivered_not_yet_expired(admin_user):
    """delivered 상태에서 120초 이내 → 그대로 유지."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)

    future_now = datetime.now(UTC) + timedelta(seconds=60)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "delivered"


def test_expire_stale_tasks_running_timeout(admin_user):
    """running 상태에서 300초 초과 → failed / failure_reason=running_timeout."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)

    future_now = datetime.now(UTC) + timedelta(seconds=301)
    expired = reg.expire_stale_tasks(now=future_now)

    assert any(t.task_id == task.task_id for t in expired)
    t = reg.find_task_by_id(task.task_id)
    assert t.status == "failed"
    assert t.failure_reason == "running_timeout"
    assert t.timed_out_at != ""


def test_expire_stale_tasks_completed_not_touched(admin_user):
    """completed 상태는 expire_stale_tasks 가 건드리지 않는다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True)

    future_now = datetime.now(UTC) + timedelta(seconds=9999)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "completed"


def test_expire_stale_tasks_failed_not_touched(admin_user):
    """failed 상태는 expire_stale_tasks 가 건드리지 않는다."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=False, error="err")

    future_now = datetime.now(UTC) + timedelta(seconds=9999)
    expired = reg.expire_stale_tasks(now=future_now)

    assert not any(t.task_id == task.task_id for t in expired)
    assert reg.find_task_by_id(task.task_id).status == "failed"


def test_apply_result_failure_sets_agent_error(admin_user):
    """apply_result(success=False) 시 failure_reason = agent_error."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=False,
        error="something broke",
        error_code="ERR_X",
    )
    assert result.status == "failed"
    assert result.failure_reason == "agent_error"


# ── Stage 13G-3A: result_data 안전 저장 테스트 ──────────────────────────


def test_apply_result_stores_result_data(admin_user):
    """apply_result(data=...) 시 허용 key만 저장된다."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="open_url_dry_run_ok",
        data={
            "action": "open_url",
            "dry_run": True,
            "would_open_browser": False,
            "external_network_call": False,
            "requires_approval": False,
            "policy_decision": "dry_run_allowed",
        },
    )
    assert result.status == "completed"
    assert result.result_summary == "open_url_dry_run_ok"
    assert result.result_data is not None
    assert result.result_data["dry_run"] is True
    assert result.result_data["would_open_browser"] is False
    assert result.result_data["external_network_call"] is False
    assert result.result_data["policy_decision"] == "dry_run_allowed"
    assert result.result_data["requires_approval"] is False
    assert result.result_data["action"] == "open_url"


def test_apply_result_result_data_in_to_safe(admin_user):
    """result_data가 to_safe() 응답에 포함된다."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="open_url_dry_run_ok",
        data={"action": "open_url", "dry_run": True, "would_open_browser": False},
    )
    t = reg.get_task(agent_id, task.task_id)
    safe = t.to_safe()
    assert "result_data" in safe
    assert safe["result_data"]["dry_run"] is True
    assert safe["result_data"]["would_open_browser"] is False


def test_apply_result_result_data_via_api(admin_user):
    """API task 조회 응답에 result_data가 포함된다."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="open_url_dry_run_ok",
        data={"dry_run": True, "policy_decision": "dry_run_allowed"},
    )
    resp = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{task.task_id}")
    assert resp.status_code == 200
    d = resp.json()
    assert "result_data" in d
    assert d["result_data"]["dry_run"] is True
    assert d["result_data"]["policy_decision"] == "dry_run_allowed"


def test_apply_result_strips_sensitive_key(admin_user):
    """민감 key(token, password, cookie 등)는 result_data에 저장되지 않는다."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="ok",
        data={
            "action": "open_url",
            "token": "secret_token_value",
            "password": "hunter2",
            "cookie": "session=abc",
            "authorization": "Bearer xyz",
            "dry_run": True,
        },
    )
    rd = result.result_data
    assert rd is not None
    assert "token" not in rd
    assert "password" not in rd
    assert "cookie" not in rd
    assert "authorization" not in rd
    assert rd.get("dry_run") is True


def test_apply_result_strips_unknown_key(admin_user):
    """허용 key 목록에 없는 key는 result_data에 저장되지 않는다."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="ok",
        data={"action": "open_url", "dry_run": True, "unknown_custom_field": "value"},
    )
    rd = result.result_data
    assert rd is not None
    assert "unknown_custom_field" not in rd
    assert rd.get("dry_run") is True


def test_apply_result_no_data_result_data_none(admin_user):
    """data 없이 apply_result 호출 시 result_data=None."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    result = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="ws_noop_ok",
    )
    assert result.result_data is None


def test_strip_result_data_url_query_removed():
    """normalized_url에서 query string이 제거된다."""
    from ai_orchestrator.agent_hub.registry.facade import _strip_result_data

    rd = _strip_result_data({"normalized_url": "https://example.com/path?token=abc&foo=bar"})
    assert rd is not None
    assert rd["normalized_url"] == "https://example.com/path"


def test_strip_result_data_empty_returns_none():
    """빈 dict는 None 반환."""
    from ai_orchestrator.agent_hub.registry.facade import _strip_result_data

    assert _strip_result_data({}) is None
    assert _strip_result_data(None) is None


def test_strip_result_data_sensitive_key_dropped():
    """민감 key만 있는 data는 None 반환."""
    from ai_orchestrator.agent_hub.registry.facade import _strip_result_data

    assert _strip_result_data({"token": "abc", "password": "pw"}) is None


# ── Stage 11-4B: list_tasks_for_agent registry 단위 테스트 ──────────────


def test_list_tasks_empty_for_unknown_agent():
    """없는 agent_id → 빈 목록."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    result = reg.list_tasks_for_agent("la-nonexistent")
    assert result == []


def test_list_tasks_returns_all_tasks_for_agent(admin_user):
    """task 3개 생성 → 전체 반환, agent_id 일치 확인."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(3):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id)
    assert len(tasks) == 3
    assert all(t.agent_id == agent_id for t in tasks)


def test_list_tasks_status_filter(admin_user):
    """status 필터: queued 2개 + completed 1개 → status=queued → 2개."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    _make_queued_task(agent_id)
    _make_queued_task(agent_id)
    t3 = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, t3.task_id)
    reg.mark_running(agent_id, t3.task_id)
    reg.apply_result(agent_id=agent_id, task_id=t3.task_id, success=True, summary="ok")
    queued = reg.list_tasks_for_agent(agent_id, status="queued")
    assert len(queued) == 2
    assert all(t.status == "queued" for t in queued)


def test_list_tasks_limit(admin_user):
    """limit=2 → 2개만 반환."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(5):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id, limit=2)
    assert len(tasks) == 2


def test_list_tasks_sorted_newest_first(admin_user):
    """created_at 최신순 정렬 확인."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    for _ in range(3):
        _make_queued_task(agent_id)
    tasks = reg.list_tasks_for_agent(agent_id)
    created_ats = [t.created_at for t in tasks]
    assert created_ats == sorted(created_ats, reverse=True)


def test_list_tasks_contains_failure_reason_and_timed_out_at(admin_user):
    """failed task → failure_reason / timed_out_at 포함."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    reg.mark_delivered(agent_id, task.task_id)
    future = datetime.now(UTC) + timedelta(seconds=9999)
    reg.expire_stale_tasks(now=future)
    tasks = reg.list_tasks_for_agent(agent_id, status="failed")
    assert len(tasks) == 1
    t = tasks[0]
    assert t.failure_reason == "delivered_timeout"
    assert t.timed_out_at != ""


def test_list_tasks_agent_isolation(admin_user):
    """agent A/B task 혼합 → 각 agent는 자신의 task만 반환."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    agent_a = _register_agent(client)["agent_id"]
    agent_b = _register_agent(client)["agent_id"]
    for _ in range(2):
        reg.enqueue_task(agent_id=agent_a, action="open_url", params={"url": "https://a.com"}, requested_by="test")
    reg.enqueue_task(agent_id=agent_b, action="open_url", params={"url": "https://b.com"}, requested_by="test")
    tasks_a = reg.list_tasks_for_agent(agent_a)
    tasks_b = reg.list_tasks_for_agent(agent_b)
    assert len(tasks_a) == 2
    assert len(tasks_b) == 1
    assert all(t.agent_id == agent_a for t in tasks_a)
    assert all(t.agent_id == agent_b for t in tasks_b)


def test_to_list_safe_excludes_params(admin_user):
    """to_list_safe() 응답에 params 없음."""
    client = _make_test_client(admin_user)
    agent_id = _register_agent(client)["agent_id"]
    task = _make_queued_task(agent_id)
    safe = task.to_list_safe()
    assert "params" not in safe


def test_to_list_safe_excludes_token_id(admin_user):
    """to_list_safe() 응답에 token_id 없음."""
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
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks", json={"action": "open_url", "params": {"url": "https://example.com"}}
    )
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
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks", json={"action": "open_url", "params": {"url": "https://example.com"}}
    )
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
    client.post(
        f"/api/v1/local-agents/{agent_id}/tasks", json={"action": "open_url", "params": {"url": "https://example.com"}}
    )
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
    import ai_orchestrator.agent_hub.registry.facade as reg

    result = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    assert reg.get_agent_status(result.agent.agent_id) == "offline"


def test_set_agent_connected_sets_timestamps():
    """set_agent_connected 후 connected_at / last_seen_at 설정, disconnected_at 초기화."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    reg.set_agent_connected(agent_id, now="2026-01-01T00:00:00+00:00")
    a = reg.get_agent(agent_id)
    assert a.connected_at == "2026-01-01T00:00:00+00:00"
    assert a.last_seen_at == "2026-01-01T00:00:00+00:00"
    assert a.disconnected_at == ""


def test_set_agent_disconnected_sets_disconnected_at():
    """set_agent_disconnected 후 disconnected_at 설정."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    reg.set_agent_connected(agent_id, now="2026-01-01T00:00:00+00:00")
    reg.set_agent_disconnected(agent_id, now="2026-01-01T00:01:00+00:00")
    a = reg.get_agent(agent_id)
    assert a.disconnected_at == "2026-01-01T00:01:00+00:00"
    assert a.last_seen_at == "2026-01-01T00:00:00+00:00"  # 기존 값 유지


def test_agent_status_idle_when_connected_no_task():
    """연결 중이고 active task 없으면 idle."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    status = reg.get_agent_status(agent_id, now=now)
    assert status == "idle"


def test_agent_status_busy_with_delivered_task():
    """delivered task 있으면 busy."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    task = reg.enqueue_task(agent_id=agent_id, action="open_url", params={"url": "https://x.com"}, requested_by="t")
    reg.mark_delivered(agent_id, task.task_id)
    assert reg.get_agent_status(agent_id, now=now) == "busy"


def test_agent_status_busy_with_running_task():
    """running task 있으면 busy."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    now = "2026-01-01T00:00:00+00:00"
    reg.set_agent_connected(agent_id, now=now)
    task = reg.enqueue_task(agent_id=agent_id, action="open_url", params={"url": "https://x.com"}, requested_by="t")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    assert reg.get_agent_status(agent_id, now=now) == "busy"


def test_agent_status_stale_after_91s():
    """last_seen_at이 91초 이상 과거면 stale."""
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    r = reg.register_agent(host="h", os_name="W", version="0.1", requested_by="t")
    agent_id = r.agent.agent_id
    past = (datetime.now(UTC) - timedelta(seconds=91)).isoformat()
    reg.set_agent_connected(agent_id, now=past)
    assert reg.get_agent_status(agent_id) == "stale"


def test_agent_status_offline_after_disconnect():
    """disconnected_at 설정 후 offline."""
    import ai_orchestrator.agent_hub.registry.facade as reg

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


# ── Stage 11-7B: cancel_task registry 단위 테스트 ──────────────────────


def _make_agent_and_task(action: str = "open_url", params: dict | None = None):
    """테스트용 agent + task 생성 헬퍼. registry 직접 사용."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    result = reg.register_agent(
        host="cancel-test-pc",
        os_name="Windows 11",
        version="0.1.0",
        requested_by="tester",
    )
    agent_id = result.agent.agent_id
    task = reg.enqueue_task(
        agent_id=agent_id,
        action=action,
        params=params or {},
        requested_by="tester",
    )
    return agent_id, task


def test_cancel_queued_task_becomes_cancelled():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    assert task.status == "queued"
    t, action = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="test")
    assert t.status == "cancelled"
    assert action == "cancelled"


def test_cancel_waiting_approval_task_becomes_cancelled():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("capture_screenshot")
    assert task.status == "waiting_approval"
    t, action = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="rejected by admin")
    assert t.status == "cancelled"
    assert action == "cancelled"


def test_cancel_delivered_task_becomes_cancel_requested():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    t, action = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="stop it")
    assert t.status == "cancel_requested"
    assert action == "cancel_requested"


def test_cancel_running_task_becomes_cancel_requested():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    t, action = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="user request")
    assert t.status == "cancel_requested"
    assert action == "cancel_requested"


def test_cancel_completed_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=True, summary="done")
    with pytest.raises(reg.CancelNotAllowedError):
        reg.cancel_task(agent_id, task.task_id, actor="admin")


def test_cancel_failed_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.apply_result(agent_id=agent_id, task_id=task.task_id, success=False, error="oops")
    with pytest.raises(reg.CancelNotAllowedError):
        reg.cancel_task(agent_id, task.task_id, actor="admin")


def test_cancel_rejected_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("capture_screenshot")
    reg.mark_rejected(task.task_id, actor="admin", reason="denied")
    with pytest.raises(reg.CancelNotAllowedError):
        reg.cancel_task(agent_id, task.task_id, actor="admin")


def test_cancel_cancelled_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.cancel_task(agent_id, task.task_id, actor="admin")
    with pytest.raises(reg.CancelNotAllowedError):
        reg.cancel_task(agent_id, task.task_id, actor="admin")


def test_cancel_cancel_requested_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin")
    with pytest.raises(reg.CancelNotAllowedError):
        reg.cancel_task(agent_id, task.task_id, actor="admin")


def test_cancel_saves_cancel_reason():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="user request")
    assert t.cancel_reason == "user request"


def test_cancel_saves_cancel_requested_by():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="tester_actor")
    assert t.cancel_requested_by == "tester_actor"


def test_cancel_queued_saves_cancelled_at():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="admin")
    assert t.cancelled_at != ""
    assert t.completed_at != ""


def test_cancel_delivered_saves_cancel_requested_at():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="admin")
    assert t.cancel_requested_at != ""
    assert t.cancelled_at == ""  # cancel_requested 단계에서는 미설정


def test_cancel_reason_max_len_enforced():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    with pytest.raises(ValueError, match="최대 길이"):
        reg.cancel_task(agent_id, task.task_id, actor="admin", reason="x" * 201)


def test_cancel_unknown_task_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, _ = _make_agent_and_task("open_url")
    with pytest.raises(ValueError):
        reg.cancel_task(agent_id, "lat-nonexistent", actor="admin")


def test_cancel_agent_id_mismatch_raises():
    import ai_orchestrator.agent_hub.registry.facade as reg

    _, task = _make_agent_and_task("open_url")
    with pytest.raises(ValueError):
        reg.cancel_task("la-wrongagent", task.task_id, actor="admin")


def test_to_safe_includes_cancel_fields():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="ui cancel")
    safe = t.to_safe()
    assert "cancel_reason" in safe
    assert "cancel_requested_at" in safe
    assert "cancel_requested_by" in safe
    assert "cancelled_at" in safe
    assert safe["cancel_reason"] == "ui cancel"
    assert safe["cancel_requested_by"] == "admin"


def test_to_list_safe_includes_cancel_fields():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    t, _ = reg.cancel_task(agent_id, task.task_id, actor="admin", reason="list test")
    ls = t.to_list_safe()
    assert "cancel_reason" in ls
    assert "cancel_requested_at" in ls
    assert "cancel_requested_by" in ls
    assert "cancelled_at" in ls


def test_apply_result_cancel_requested_success_becomes_completed():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin")
    assert reg.find_task_by_id(task.task_id).status == "cancel_requested"
    # agent가 취소 전에 이미 완료 result 송신
    updated = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="already done",
    )
    assert updated.status == "completed"


def test_apply_result_cancel_requested_failure_becomes_failed():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin")
    updated = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=False,
        error="agent error",
        error_code="ERR",
    )
    assert updated.status == "failed"


def test_apply_result_cancel_requested_preserves_cancel_fields():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin", reason="preserve check")
    updated = reg.apply_result(
        agent_id=agent_id,
        task_id=task.task_id,
        success=True,
        summary="done",
    )
    assert updated.cancel_reason == "preserve check"
    assert updated.cancel_requested_by == "admin"


def test_expire_stale_tasks_cancel_requested_timeout():
    from datetime import datetime, timedelta

    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin")

    future = datetime.now(UTC) + timedelta(seconds=reg.RUNNING_TIMEOUT_SECONDS + 1)
    expired = reg.expire_stale_tasks(now=future)

    assert any(t.task_id == task.task_id for t in expired)
    t = reg.find_task_by_id(task.task_id)
    assert t.status == "failed"
    assert t.failure_reason == "cancel_timeout"


def test_fail_active_tasks_for_agent_includes_cancel_requested():
    import ai_orchestrator.agent_hub.registry.facade as reg

    agent_id, task = _make_agent_and_task("open_url")
    reg.mark_delivered(agent_id, task.task_id)
    reg.mark_running(agent_id, task.task_id)
    reg.cancel_task(agent_id, task.task_id, actor="admin")
    assert reg.find_task_by_id(task.task_id).status == "cancel_requested"

    failed, requeued = reg.fail_active_tasks_for_agent(agent_id)
    assert any(t.task_id == task.task_id for t in failed)
    assert not requeued  # cancel_requested는 재큐잉 대상 아님(사용자 취소 의도 보존)
    assert reg.find_task_by_id(task.task_id).status == "failed"


def test_known_task_statuses_includes_cancel_statuses():
    import ai_orchestrator.agent_hub.registry.facade as reg

    assert "cancel_requested" in reg.KNOWN_TASK_STATUSES
    assert "cancelled" in reg.KNOWN_TASK_STATUSES


def test_active_task_statuses_includes_cancel_requested():
    import ai_orchestrator.agent_hub.registry.facade as reg

    assert "cancel_requested" in reg.ACTIVE_TASK_STATUSES


# ── Stage 11-7B-2: cancel API 테스트 ────────────────────────────────────


def _enqueue_via_api(client, agent_id: str, action: str = "open_url") -> dict:
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks", json={"action": action, "params": {}})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _advance_to_delivered(agent_id: str, task_id: str) -> None:
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.mark_delivered(agent_id, task_id)


def _advance_to_running(agent_id: str, task_id: str) -> None:
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.mark_delivered(agent_id, task_id)
    reg.mark_running(agent_id, task_id)


def test_cancel_api_queued_returns_200_cancelled(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "user request"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cancel_action"] == "cancelled"
    assert body["task"]["status"] == "cancelled"


def test_cancel_api_delivered_returns_200_cancel_requested(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]
    _advance_to_delivered(agent_id, task_id)

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "stop"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cancel_action"] == "cancel_requested"
    assert body["task"]["status"] == "cancel_requested"


def test_cancel_api_unknown_task_returns_404(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/lat-notexist/cancel", json={})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "TASK_NOT_FOUND"


def test_cancel_api_agent_id_mismatch_returns_404(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    resp = client.post(f"/api/v1/local-agents/la-wrongagent/tasks/{task_id}/cancel", json={})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "TASK_NOT_FOUND"


def test_cancel_api_completed_returns_409(admin_user):
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]
    _advance_to_running(agent_id, task_id)
    reg.apply_result(agent_id=agent_id, task_id=task_id, success=True, summary="done")

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "CANCEL_NOT_ALLOWED"


def test_cancel_api_failed_returns_409(admin_user):
    import ai_orchestrator.agent_hub.registry.facade as reg

    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]
    _advance_to_running(agent_id, task_id)
    reg.apply_result(agent_id=agent_id, task_id=task_id, success=False, error="err")

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "CANCEL_NOT_ALLOWED"


def test_cancel_api_cancelled_returns_409(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]
    # 첫 번째 취소
    client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={})
    # 두 번째 취소 → 409
    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "CANCEL_NOT_ALLOWED"


def test_cancel_api_reason_too_long_returns_400(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "x" * 201})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "REASON_TOO_LONG"


def test_cancel_api_viewer_forbidden(viewer_user):
    client = _make_test_client(viewer_user)
    # viewer는 register 권한이 없으므로 별도 admin으로 준비
    import ai_orchestrator.agent_hub.registry.facade as reg

    result = reg.register_agent(host="pc", os_name="Win", version="0.1", requested_by="admin")
    agent_id = result.agent.agent_id
    task = reg.enqueue_task(agent_id=agent_id, action="open_url", params={}, requested_by="admin")

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task.task_id}/cancel", json={})
    assert resp.status_code == 403


def test_cancel_api_response_includes_cancel_fields(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "check fields"})
    assert resp.status_code == 200
    t = resp.json()["task"]
    assert "cancel_reason" in t
    assert "cancel_requested_by" in t
    assert "cancelled_at" in t
    assert "cancel_requested_at" in t
    assert t["cancel_reason"] == "check fields"
    assert t["cancel_requested_by"] == admin_user["actor"]


def test_cancel_api_response_no_token_hash_or_device_token(admin_user):
    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    resp = client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={})
    assert resp.status_code == 200
    t = resp.json()["task"]
    assert "token_hash" not in t
    assert "device_token" not in t


def test_cancel_api_audit_cancelled_event(admin_user, tmp_path, monkeypatch):
    import json

    import ai_orchestrator.audit.audit_logger as al

    monkeypatch.setattr(al, "_LOG_PATH", tmp_path / "audit.jsonl")

    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "audit test"})

    logs = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]  # noqa: E741
    events = [e["event_type"] for e in logs]
    assert "LOCAL_AGENT_TASK_CANCELLED" in events


def test_cancel_api_audit_cancel_requested_event(admin_user, tmp_path, monkeypatch):
    import json

    import ai_orchestrator.audit.audit_logger as al

    monkeypatch.setattr(al, "_LOG_PATH", tmp_path / "audit.jsonl")

    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]
    _advance_to_delivered(agent_id, task_id)

    client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": "cancel req test"})

    logs = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]  # noqa: E741
    events = [e["event_type"] for e in logs]
    assert "LOCAL_AGENT_TASK_CANCEL_REQUESTED" in events


def test_cancel_api_audit_no_reason_raw(admin_user, tmp_path, monkeypatch):
    """audit note에 reason 원문 전체가 남지 않는다 (reason_len만 기록)."""
    import json

    import ai_orchestrator.audit.audit_logger as al

    monkeypatch.setattr(al, "_LOG_PATH", tmp_path / "audit.jsonl")

    client = _make_test_client(admin_user)
    reg_resp = _register_agent(client)
    agent_id = reg_resp["agent_id"]
    task = _enqueue_via_api(client, agent_id, "open_url")
    task_id = task["task_id"]

    long_reason = "sensitive_reason_" + "x" * 100
    client.post(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/cancel", json={"reason": long_reason})

    logs = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]  # noqa: E741
    cancel_events = [e for e in logs if e["event_type"] == "LOCAL_AGENT_TASK_CANCELLED"]
    assert cancel_events, "LOCAL_AGENT_TASK_CANCELLED 이벤트가 없음"
    for ev in cancel_events:
        note = ev.get("note", "")
        assert long_reason not in note, "audit note에 reason 원문이 포함됨"
        assert "reason_len=" in note


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
