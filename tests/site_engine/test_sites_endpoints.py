"""사이트 자동화 엔드포인트 권한/audit 스모크.

검증 포인트:
- /api/v1/connectors 는 admin/owner 만 허용 (viewer/operator 403)
- /api/v1/site-health 전체/단일 조회 권한 동일
- /api/v1/site-tasks/dry-run 은 operator 이상 허용, viewer 는 403
- dry-run 은 실제 실행 없이 dry_run status 반환
- 존재하지 않는 커넥터 → 404
- 지원하지 않는 action → 400
- 감사 로그에 비밀번호/Authorization/쿠키 원문이 섞이지 않는다.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    users_path = tmp_path_factory.mktemp("policies") / "http_users.json"
    users_path.write_text(
        json.dumps(
            [
                {"username": "owner_u", "password_hash": "pw-owner", "role": "owner", "enabled": True},
                {"username": "admin_u", "password_hash": "pw-admin", "role": "admin", "enabled": True},
                {"username": "operator_u", "password_hash": "pw-operator", "role": "operator", "enabled": True},
                {"username": "viewer_u", "password_hash": "pw-viewer", "role": "viewer", "enabled": True},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from tests.conftest import apply_basic_auth_users

    mp = pytest.MonkeyPatch()
    apply_basic_auth_users(mp, users_path)
    from ai_orchestrator.core import config as _config

    importlib.reload(_config)
    from ai_orchestrator.sites import router as _sites_router

    importlib.reload(_sites_router)
    from ai_orchestrator.routers import registry as _router

    importlib.reload(_router)
    from ai_orchestrator import asgi as _server

    importlib.reload(_server)

    from fastapi.testclient import TestClient

    c = TestClient(_server.app, raise_server_exceptions=True)
    yield c

    mp.undo()
    importlib.reload(_config)
    importlib.reload(_sites_router)
    importlib.reload(_router)
    importlib.reload(_server)


def _auth(username: str) -> tuple:
    return (username, f"pw-{username.split('_')[0]}")


# ── GET /connectors ───────────────────────────────────────────────
def test_connectors_requires_auth(client):
    r = client.get("/api/v1/connectors")
    assert r.status_code == 401


def test_connectors_viewer_forbidden(client):
    r = client.get("/api/v1/connectors", auth=_auth("viewer_u"))
    assert r.status_code == 403


def test_connectors_operator_forbidden(client):
    r = client.get("/api/v1/connectors", auth=_auth("operator_u"))
    assert r.status_code == 403


def test_connectors_admin_ok(client):
    r = client.get("/api/v1/connectors", auth=_auth("admin_u"))
    assert r.status_code == 200
    data = r.json()
    names = {c["name"] for c in data["connectors"]}
    assert "dummy" in names and "example_portal" in names


# ── GET /site-health ─────────────────────────────────────────────
def test_site_health_all_viewer_forbidden(client):
    r = client.get("/api/v1/site-health", auth=_auth("viewer_u"))
    assert r.status_code == 403


def test_site_health_all_admin_ok(client):
    r = client.get("/api/v1/site-health", auth=_auth("admin_u"))
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 2
    for item in data["results"]:
        assert "state" in item and "site_name" in item


def test_site_health_one_not_found(client):
    r = client.get("/api/v1/site-health/nonexistent_site", auth=_auth("admin_u"))
    assert r.status_code == 404


def test_site_health_one_dummy_ok(client):
    r = client.get("/api/v1/site-health/dummy", auth=_auth("owner_u"))
    assert r.status_code == 200
    data = r.json()
    assert data["site_name"] == "dummy"
    assert data["state"] in {"healthy", "degraded"}


# ── POST /site-tasks/dry-run ─────────────────────────────────────
def _dry_run_body(action: str = "ping", target_site: str = "dummy") -> dict:
    return {
        "task_id": f"DRY-{uuid.uuid4().hex[:8]}",
        "target_site": target_site,
        "action": action,
        "params": {"q": "example"},
        "risk_level": "low",
        "requires_approval": False,
    }


def test_dry_run_requires_auth(client):
    r = client.post("/api/v1/site-tasks/dry-run", json=_dry_run_body())
    assert r.status_code == 401


def test_dry_run_viewer_forbidden(client):
    r = client.post("/api/v1/site-tasks/dry-run", json=_dry_run_body(), auth=_auth("viewer_u"))
    assert r.status_code == 403


def test_dry_run_operator_ok(client):
    body = _dry_run_body()
    r = client.post("/api/v1/site-tasks/dry-run", json=body, auth=_auth("operator_u"))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "dry_run"
    assert data["task_id"] == body["task_id"]
    assert data["target_site"] == "dummy"


def test_dry_run_unsupported_action_returns_400(client):
    body = _dry_run_body(action="submit_destructive_thing")
    r = client.post("/api/v1/site-tasks/dry-run", json=body, auth=_auth("admin_u"))
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["status"] == "unsupported_action"
    assert detail["error_code"] == "UNSUPPORTED_ACTION"


def test_dry_run_unknown_site_returns_404(client):
    body = _dry_run_body(target_site="no_such_site")
    r = client.post("/api/v1/site-tasks/dry-run", json=body, auth=_auth("admin_u"))
    assert r.status_code == 404


# ── 감사 로그 비민감성 ───────────────────────────────────────────
def test_audit_log_does_not_leak_secrets(client):
    """dry-run 및 health 호출 시 감사 로그에 password/Authorization/cookie 원문 금지."""
    from ai_orchestrator.audit.audit_logger import read_recent_logs

    # 호출 흔적 남기기
    body = _dry_run_body()
    body["params"] = {"password": "SHOULD_NOT_LEAK_42", "username": "alice"}
    r = client.post("/api/v1/site-tasks/dry-run", json=body, auth=_auth("admin_u"))
    assert r.status_code == 200

    client.get("/api/v1/site-health", auth=_auth("admin_u"))

    logs = read_recent_logs(limit=200)
    blob = json.dumps(logs, ensure_ascii=False).lower()
    forbidden_substrings = [
        "should_not_leak_42",  # 민감 value 자체
        "authorization:",
        "basic pw-",  # 기본 인증 헤더 원문 금지
        "set-cookie",
    ]
    for s in forbidden_substrings:
        assert s not in blob, f"감사 로그에 민감 문자열 포함됨: {s}"


def test_audit_log_records_site_events(client):
    from ai_orchestrator.audit.audit_logger import read_recent_logs

    r = client.get("/api/v1/site-health/dummy", auth=_auth("admin_u"))
    assert r.status_code == 200

    logs = read_recent_logs(limit=200)
    kinds = {e.get("event_type") for e in logs[-50:]}
    assert "SITE_HEALTH_CHECK" in kinds


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
