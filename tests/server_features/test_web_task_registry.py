"""웹 작업 레지스트리 + 표준 실행 API 검증.

필수 테스트:
  1. registry API 가 등록된 3개 작업 반환
  2. 알 수 없는 provider/action_type 거절 (404)
  3. dry_run=true 면 approval 생성 없음
  4. dry_run=true 면 submit 호출 없음
  5. dry_run=false 면 pending approval 생성
  6. viewer 는 run API 403
  7. admin/owner 는 run API 가능
  8. params 민감정보가 audit log / API 응답에 노출되지 않음
  9. validate_params 실패 시 FORM_FIELD_MISSING 반환
 10. 기존 dev_reg 승인 게이트 회귀 없음
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── 공통 픽스처 ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """각 테스트마다 독립된 storage 경로 사용.

    저장소 경로는 기존 모듈 객체의 속성을 monkeypatch 로 교체한다
    (reload 대신 속성 교체 — 동일 __globals__ 를 쓰는 함수가 즉시 반영).

    auth(`tools.gates.auth`)는 reload 하지 않는다 — 어느 시험도 reload 하지 않으면
    `get_current_user` 함수 객체가 세션 내내 안정적이라, 아래 `_make_client` 가 object-identity 기준
    `dependency_overrides` 를 써도 이미 import 된 `web_task_router` 의 라우트 의존성과 항상 같은
    객체를 가리킨다(2026-10-08 B11: reload 방식은 다른 시험까지 깨뜨려 제거함).
    """
    import ai_orchestrator.audit.audit_logger as _al
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra
    import tools.gates.approval as _ap

    monkeypatch.setattr(_al, "_LOG_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(_dra, "_STORE_PATH", tmp_path / "dev_reg_approvals.jsonl")
    monkeypatch.setattr(_ap, "_STORE_PATH", tmp_path / "approval_tokens.jsonl")

    _dra.clear()
    _ap._store.clear()
    _ap.clear_rate_store()

    yield

    _dra.clear()
    _ap._store.clear()
    _ap.clear_rate_store()


@pytest.fixture
def admin_user():
    return {"actor": "admin_test", "role": "admin"}


@pytest.fixture
def owner_user():
    return {"actor": "owner_test", "role": "owner"}


@pytest.fixture
def viewer_user():
    return {"actor": "viewer_test", "role": "viewer"}


def _make_test_client(user_override: dict):
    """지정된 user 를 반환하는 get_current_user 를 주입한 TestClient 생성.

    web_task_router 의 prefix 가 /web-tasks 이므로
    include_router(prefix="/api/v1") 후 최종 경로는 /api/v1/web-tasks/…
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.web_task.web_task_router import web_task_router
    from tools.gates.auth import get_current_user

    test_app = FastAPI()
    test_app.include_router(web_task_router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(test_app, raise_server_exceptions=True)


# ── 테스트 1: registry 가 3개 작업 반환 ─────────────────────────────


def test_registry_returns_three_tasks(admin_user):
    """GET /api/v1/web-tasks/registry 가 등록된 3개 작업을 반환한다."""
    client = _make_test_client(admin_user)
    resp = client.get("/api/v1/web-tasks/registry")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 3
    task_keys = {t["task_key"] for t in tasks}
    assert "hiworks/developer_apply" in task_keys
    assert "naver/app_register" in task_keys
    assert "google/oauth_submit" in task_keys


def test_registry_tasks_have_required_fields(admin_user):
    """registry 각 항목에 필수 필드가 존재하며 adapter_class 는 노출되지 않는다."""
    client = _make_test_client(admin_user)
    tasks = client.get("/api/v1/web-tasks/registry").json()["tasks"]
    required = {"task_key", "provider", "action_type", "risk_level", "requires_approval", "read_only", "description"}
    for t in tasks:
        assert required <= t.keys(), f"필드 누락: {required - t.keys()}"
        assert "adapter_class" not in t, "adapter_class 가 응답에 노출됨"


# ── 테스트 2: 미등록 작업 거절 ──────────────────────────────────────


def test_unknown_provider_rejected(admin_user):
    """미등록 provider → 404 + UNKNOWN_TASK."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "unknown_provider",
            "action_type": "developer_apply",
            "params": {"app_name": "TestApp"},
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "UNKNOWN_TASK"


def test_unknown_action_type_rejected(admin_user):
    """미등록 action_type → 404."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "nonexistent_action",
            "params": {"app_name": "TestApp"},
        },
    )
    assert resp.status_code == 404


def test_unknown_task_audit_logged(admin_user):
    """미등록 작업 시도가 WEB_TASK_REJECTED_UNKNOWN_TASK 로 기록된다."""
    client = _make_test_client(admin_user)
    client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "unknown",
            "action_type": "unknown",
            "params": {"app_name": "Test"},
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_REJECTED_UNKNOWN_TASK" in events


# ── 테스트 3: dry_run=true → approval 생성 없음 ──────────────────────


def test_dry_run_no_approval_created(admin_user):
    """dry_run=true 이면 dev_reg_approval 레코드가 생성되지 않는다."""
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"app_name": "TestApp"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    assert _dra.list_pending() == []


# ── 테스트 4: dry_run=true → submit 호출 없음 ───────────────────────


def test_dry_run_no_submit_called(admin_user):
    """dry_run=true 이면 submit_form 이 호출되지 않는다."""
    with patch("ai_orchestrator.sites.adapters.hiworks_dev_reg.HiworksDevRegAdapter.submit_form") as mock_submit:
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {"app_name": "TestApp"},
                "dry_run": True,
            },
        )
        assert resp.status_code == 200
        mock_submit.assert_not_called()


def test_dry_run_returns_summary(admin_user):
    """dry_run=true 이면 summary 와 field_names 가 응답에 포함된다."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"app_name": "MyTestApp", "company_name": "TestCo"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["success"] is True
    assert "DRY RUN" in data["summary"]
    assert "app_name" in data["field_names"]


# ── 테스트 5: dry_run=false → pending approval 생성 ─────────────────


def test_real_run_creates_pending_approval(admin_user):
    """dry_run=false 이면 pending approval 레코드가 생성된다."""
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "naver",
                "action_type": "app_register",
                "params": {"app_name": "NaverTestApp"},
                "dry_run": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    task_id = data["task_id"]
    assert task_id.startswith("wt-")

    pending = _dra.list_pending()
    assert len(pending) == 1
    assert pending[0]["task_id"] == task_id
    assert pending[0]["provider"] == "naver"
    assert pending[0]["status"] == "pending"


def test_real_run_response_fields(admin_user):
    """dry_run=false 응답에 필수 필드가 포함된다."""
    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {"app_name": "FieldTest"},
                "dry_run": False,
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    for field in (
        "dry_run",
        "status",
        "task_id",
        "provider",
        "action_type",
        "risk_level",
        "requires_approval",
        "expires_at",
    ):
        assert field in data, f"응답 필드 누락: {field}"


# ── 테스트 6: viewer → run/registry API 403 ─────────────────────────


def test_viewer_run_forbidden(viewer_user):
    """viewer 역할은 run API 에 403 을 받는다."""
    client = _make_test_client(viewer_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"app_name": "TestApp"},
        },
    )
    assert resp.status_code == 403


def test_viewer_registry_forbidden(viewer_user):
    """viewer 역할은 registry API 에 403 을 받는다."""
    client = _make_test_client(viewer_user)
    resp = client.get("/api/v1/web-tasks/registry")
    assert resp.status_code == 403


# ── 테스트 7: admin/owner → run/registry API 가능 ───────────────────


def test_admin_can_call_run(admin_user):
    """admin 역할은 run API (dry_run=true) 를 호출할 수 있다."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "google",
            "action_type": "oauth_submit",
            "params": {"app_name": "GoogleTestApp"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200


def test_owner_can_call_registry(owner_user):
    """owner 역할은 registry API 를 호출할 수 있다."""
    client = _make_test_client(owner_user)
    resp = client.get("/api/v1/web-tasks/registry")
    assert resp.status_code == 200


# ── 테스트 8: 민감정보 audit log / 응답 미노출 ──────────────────────


def test_sensitive_params_not_in_response(admin_user):
    """params 의 민감 필드(password, cookie 등)가 API 응답에 포함되지 않는다."""
    _SENSITIVE = "ultra_secret_password_xyz123"

    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {
                    "app_name": "TestApp",
                    "password": _SENSITIVE,
                    "cookie": "raw_cookie_value_abc",
                },
                "dry_run": False,
            },
        )

    assert resp.status_code == 200
    assert _SENSITIVE not in resp.text
    assert "raw_cookie_value_abc" not in resp.text


def test_sensitive_params_not_in_audit_log(admin_user, tmp_path):
    """params 의 민감 필드가 감사 로그에 포함되지 않는다."""
    _SENSITIVE = "my_super_secret_token_98765"

    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {
                    "app_name": "LogTestApp",
                    "session_token": _SENSITIVE,
                },
                "dry_run": False,
            },
        )

    import ai_orchestrator.audit.audit_logger as _al

    log_path = _al._LOG_PATH
    if not log_path.exists():
        return
    raw = log_path.read_text(encoding="utf-8")
    assert _SENSITIVE not in raw, "민감값이 감사 로그에 노출됨"


def test_dry_run_sensitive_params_not_in_summary(admin_user):
    """dry_run=true 시 민감 params 가 summary 에 포함되지 않는다."""
    _SENSITIVE = "leak_test_password_abc"

    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {
                "app_name": "SensitiveTest",
                "password": _SENSITIVE,
            },
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    assert _SENSITIVE not in resp.text


# ── 테스트 9: validate_params 실패 → FORM_FIELD_MISSING ─────────────


def test_missing_app_name_returns_validation_error(admin_user):
    """app_name 누락 시 422 + FORM_FIELD_MISSING 반환."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"company_name": "TestCo"},  # app_name 없음
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "FORM_FIELD_MISSING"


def test_validation_failure_audit_logged(admin_user):
    """검증 실패 시 WEB_TASK_VALIDATION_FAILED 이벤트가 기록된다."""
    client = _make_test_client(admin_user)
    client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {},  # app_name 없음
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_VALIDATION_FAILED" in events


# ── 테스트 10: 기존 dev_reg 회귀 없음 ───────────────────────────────


def test_dev_reg_approval_imports_unchanged():
    """기존 dev_reg_approval 핵심 함수가 정상 임포트된다."""
    from ai_orchestrator.dev_reg.dev_reg_approval import (
        create_pending,
        handle_telegram_decision,
        list_pending,
        register_approval_waiter,
        signal_approval_event,
    )

    for fn in (create_pending, list_pending, handle_telegram_decision, register_approval_waiter, signal_approval_event):
        assert callable(fn)


def test_dev_reg_runner_imports_unchanged():
    """기존 dev_reg_runner 가 정상 임포트된다."""
    from ai_orchestrator.dev_reg.dev_reg_runner import DevRegResult, run_dev_reg

    assert callable(run_dev_reg)
    assert DevRegResult is not None


def test_existing_adapter_imports_unchanged():
    """기존 어댑터 3개가 정상 임포트되고 필수 메서드를 가진다."""
    from ai_orchestrator.sites.adapters.google_dev_reg import GoogleDevRegAdapter
    from ai_orchestrator.sites.adapters.hiworks_dev_reg import HiworksDevRegAdapter
    from ai_orchestrator.sites.adapters.naver_dev_reg import NaverDevRegAdapter

    for cls in (HiworksDevRegAdapter, NaverDevRegAdapter, GoogleDevRegAdapter):
        adapter = cls()
        assert hasattr(adapter, "fill_form")
        assert hasattr(adapter, "submit_form")
        assert hasattr(adapter, "abort_form")


def test_registry_does_not_break_existing_adapters():
    """web_task_registry 가 기존 어댑터와 정상 연동된다."""
    from ai_orchestrator.web_task.web_task_registry import get_entry, list_entries

    assert get_entry("hiworks", "developer_apply") is not None
    assert get_entry("naver", "app_register") is not None
    assert get_entry("google", "oauth_submit") is not None
    assert get_entry("unknown", "unknown") is None
    assert len(list_entries()) == 3


# ── 추가: 감사 로그 이벤트 검증 ─────────────────────────────────────


def test_dry_run_audit_event_recorded(admin_user):
    """dry_run=true 시 WEB_TASK_DRY_RUN_COMPLETED 이벤트가 기록된다."""
    client = _make_test_client(admin_user)
    client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"app_name": "AuditTest"},
            "dry_run": True,
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_DRY_RUN_COMPLETED" in events


def test_real_run_audit_events_recorded(admin_user):
    """dry_run=false 시 WEB_TASK_RUN_REQUESTED + WEB_TASK_PENDING_APPROVAL_CREATED 기록."""
    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        client.post(
            "/api/v1/web-tasks/run",
            json={
                "provider": "hiworks",
                "action_type": "developer_apply",
                "params": {"app_name": "AuditRealTest"},
                "dry_run": False,
            },
        )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_RUN_REQUESTED" in events
    assert "WEB_TASK_PENDING_APPROVAL_CREATED" in events


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
