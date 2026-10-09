"""웹 작업 템플릿 + 간편 실행 인터페이스 검증 (Stage 3).

필수 테스트:
  1. templates API 가 등록된 3개 템플릿 반환
  2. default_params 원문이 응답에 노출되지 않음 (default_param_keys 만)
  3. run-from-template dry_run=true 성공
  4. override_params 가 default_params 와 정상 병합 (override 우선)
  5. 없는 template_id → 404 + TEMPLATE_NOT_FOUND
  6. dry_run=false → pending approval 생성
  7. override_params 의 민감 필드가 응답/감사 로그에 노출되지 않음
  8. validate_params 실패 시 missing_fields + FORM_FIELD_MISSING 반환
  9. viewer 역할은 templates / run-from-template API 403
 10. 기존 web-task 테스트 회귀 없음 (별도 suite 동시 실행으로 검증)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── 공통 픽스처 (test_web_task_registry.py 와 동일 패턴 — auth 는 reload 하지 않는다,
# 2026-10-08 B11: 어느 시험도 gates.auth 를 reload 하지 않으면 get_current_user 가 세션 내내
# 안정적이라 dependency_overrides 가 항상 같은 객체를 가리킨다) ────────────────


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
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
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.web_task.web_task_router import web_task_router
    from tools.gates.auth import get_current_user

    test_app = FastAPI()
    test_app.include_router(web_task_router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: user_override
    return TestClient(test_app, raise_server_exceptions=True)


# ── 1. templates API 가 3개 템플릿 반환 ─────────────────────────────────


def test_templates_api_returns_three_templates(admin_user):
    client = _make_test_client(admin_user)
    resp = client.get("/api/v1/web-tasks/templates")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) == 3
    ids = {t["template_id"] for t in templates}
    assert {"hiworks_default", "naver_default", "google_default"} <= ids


def test_templates_have_required_fields(admin_user):
    client = _make_test_client(admin_user)
    templates = client.get("/api/v1/web-tasks/templates").json()["templates"]
    required = {"template_id", "provider", "action_type", "description", "required_fields", "default_param_keys"}
    for t in templates:
        assert required <= t.keys(), f"필드 누락: {required - t.keys()}"


# ── 2. default_params 원문 미노출 ───────────────────────────────────────


def test_templates_default_params_not_exposed_raw(admin_user):
    """templates API 는 default_param_keys 만 반환, default_params 원문 금지."""
    client = _make_test_client(admin_user)
    body = client.get("/api/v1/web-tasks/templates").json()
    raw = client.get("/api/v1/web-tasks/templates").text
    for t in body["templates"]:
        assert "default_params" not in t, "default_params 원문이 응답에 노출됨"
        assert isinstance(t["default_param_keys"], list)
    # 알려진 default 값(예: "내부 자동화 연동")이 응답 본문에 직접 포함되지 않아야 한다
    assert "내부 자동화 연동" not in raw


def test_no_secret_keys_in_template_default_params():
    """템플릿 모듈 자체에 민감 키가 default_params 로 등록돼 있으면 안 된다."""
    from ai_orchestrator.web_task.web_task_templates import _FORBIDDEN_KEYS, _TEMPLATES

    for t in _TEMPLATES.values():
        keys = {k.lower() for k in t.default_params}
        leaked = keys & _FORBIDDEN_KEYS
        assert not leaked, f"템플릿 {t.template_id} 에 민감 키 노출: {leaked}"


# ── 3. run-from-template dry_run 성공 ──────────────────────────────────


def test_run_from_template_dry_run_success(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "hiworks_default",
            "override_params": {"app_name": "TplApp"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["dry_run"] is True
    assert data["template_id"] == "hiworks_default"
    assert data["provider"] == "hiworks"
    assert data["action_type"] == "developer_apply"
    assert data["success"] is True
    assert "DRY RUN" in data["summary"]


def test_run_from_template_dry_run_no_approval_created(admin_user):
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "naver_default",
            "override_params": {"app_name": "DryNaver"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    assert _dra.list_pending() == []


# ── 4. override_params 병합 정상 ───────────────────────────────────────


def test_override_params_merge(admin_user):
    """override_params 가 default_params 의 같은 키를 덮어쓴다.

    summary 에 노출되는 service_url 키를 override 해 실제 적용 여부를 확인한다.
    (어댑터 summary 화이트리스트 — _SAFE_SUMMARY_FIELDS — 에 포함된 필드만
    summary 텍스트에 등장하므로 service_url 로 검증한다.)
    """
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "naver_default",
            "override_params": {
                "app_name": "OverrideApp",
                "service_url": "https://override.example.com",
            },
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert "OverrideApp" in summary
    assert "override.example.com" in summary
    # default service_url(haehan-ai.kr) 가 살아 있으면 안 됨
    assert "haehan-ai.kr" not in summary


def test_default_params_used_when_override_missing(admin_user):
    """override_params 에 없는 default 값은 그대로 사용된다."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "naver_default",
            "override_params": {"app_name": "OnlyAppName"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    # default service_url 은 https://haehan-ai.kr
    assert "haehan-ai.kr" in summary


# ── 5. 없는 template_id → 404 ──────────────────────────────────────────


def test_unknown_template_id_returns_404(admin_user):
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "does_not_exist",
            "override_params": {"app_name": "X"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "TEMPLATE_NOT_FOUND"


def test_unknown_template_id_audit_logged(admin_user):
    client = _make_test_client(admin_user)
    client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "no_such_template",
            "override_params": {},
            "dry_run": True,
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_TEMPLATE_NOT_FOUND" in events


# ── 6. dry_run=false → pending approval 생성 ──────────────────────────


def test_run_from_template_real_run_creates_pending_approval(admin_user):
    import ai_orchestrator.dev_reg.dev_reg_approval as _dra

    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run-from-template",
            json={
                "template_id": "google_default",
                "override_params": {"app_name": "RealRunApp"},
                "dry_run": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["template_id"] == "google_default"
    pending = _dra.list_pending()
    assert len(pending) == 1
    assert pending[0]["provider"] == "google"


def test_template_used_audit_event_recorded(admin_user):
    client = _make_test_client(admin_user)
    client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "hiworks_default",
            "override_params": {"app_name": "AuditTplApp"},
            "dry_run": True,
        },
    )
    import ai_orchestrator.audit.audit_logger as _al

    events = {e["event_type"] for e in _al.read_recent_logs(limit=50)}
    assert "WEB_TASK_TEMPLATE_USED" in events


# ── 7. 민감정보 미노출 ─────────────────────────────────────────────────


def test_sensitive_override_not_in_response(admin_user):
    _SECRET = "leak_template_secret_xyz999"  # noqa: S105
    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        resp = client.post(
            "/api/v1/web-tasks/run-from-template",
            json={
                "template_id": "hiworks_default",
                "override_params": {
                    "app_name": "SecretTpl",
                    "password": _SECRET,
                    "client_secret": "another_secret_to_hide",
                },
                "dry_run": False,
            },
        )
    assert resp.status_code == 200
    assert _SECRET not in resp.text
    assert "another_secret_to_hide" not in resp.text


def test_sensitive_override_not_in_audit_log(admin_user):
    _SECRET = "audit_template_secret_pqr"  # noqa: S105
    with patch("ai_orchestrator.core.telegram_sender.send_message", return_value={"ok": False, "skipped": True}):
        client = _make_test_client(admin_user)
        client.post(
            "/api/v1/web-tasks/run-from-template",
            json={
                "template_id": "hiworks_default",
                "override_params": {
                    "app_name": "AuditSecretTpl",
                    "session_token": _SECRET,
                },
                "dry_run": False,
            },
        )
    import ai_orchestrator.audit.audit_logger as _al

    log_path = _al._LOG_PATH
    if not log_path.exists():
        return
    raw = log_path.read_text(encoding="utf-8")
    assert _SECRET not in raw, "민감 override 가 감사 로그에 노출됨"


# ── 8. validate_params 실패 시 missing_fields 반환 ────────────────────


def test_run_from_template_missing_app_name_returns_missing_fields(admin_user):
    """default 에 app_name 이 없고 override 에도 없으면 missing_fields 반환."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "hiworks_default",
            "override_params": {},  # app_name 없음
            "dry_run": True,
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error_code"] == "FORM_FIELD_MISSING"
    assert "app_name" in detail["missing_fields"]
    assert isinstance(detail["invalid_fields"], list)


def test_run_endpoint_missing_app_name_returns_missing_fields(admin_user):
    """기존 /run 엔드포인트도 missing_fields/error_code 를 함께 반환한다."""
    client = _make_test_client(admin_user)
    resp = client.post(
        "/api/v1/web-tasks/run",
        json={
            "provider": "hiworks",
            "action_type": "developer_apply",
            "params": {"company_name": "Co"},  # app_name 없음
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error_code"] == "FORM_FIELD_MISSING"
    assert detail["error"] == "FORM_FIELD_MISSING"  # 기존 호환
    assert detail["missing_fields"] == ["app_name"]


# ── 9. viewer 접근 403 ──────────────────────────────────────────────────


def test_viewer_templates_forbidden(viewer_user):
    client = _make_test_client(viewer_user)
    resp = client.get("/api/v1/web-tasks/templates")
    assert resp.status_code == 403


def test_viewer_run_from_template_forbidden(viewer_user):
    client = _make_test_client(viewer_user)
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "hiworks_default",
            "override_params": {"app_name": "X"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 403


def test_owner_can_use_templates(owner_user):
    client = _make_test_client(owner_user)
    resp = client.get("/api/v1/web-tasks/templates")
    assert resp.status_code == 200
    resp = client.post(
        "/api/v1/web-tasks/run-from-template",
        json={
            "template_id": "naver_default",
            "override_params": {"app_name": "OwnerTplApp"},
            "dry_run": True,
        },
    )
    assert resp.status_code == 200


# ── 10. 모듈 단위 sanity ────────────────────────────────────────────────


def test_templates_module_get_template_lookup():
    from ai_orchestrator.web_task.web_task_templates import get_template

    assert get_template("hiworks_default") is not None
    assert get_template("naver_default") is not None
    assert get_template("google_default") is not None
    assert get_template("missing") is None
    assert get_template("") is None


def test_merge_params_override_wins():
    from ai_orchestrator.web_task.web_task_templates import get_template, merge_params

    t = get_template("naver_default")
    merged = merge_params(t, {"company_name": "Z", "app_name": "A"})
    assert merged["company_name"] == "Z"
    assert merged["app_name"] == "A"
    # default 키는 유지
    assert merged.get("service_url") == "https://haehan-ai.kr"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
