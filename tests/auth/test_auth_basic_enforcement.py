"""Stage AUTH-IMPL-1: app-level Basic Auth enforcement 회귀.

검증 대상:
  - AUTH_ENABLED=False  → dummy owner (내부 MVP 호환)
  - AUTH_ENABLED=True   → 인증 강제, salted SHA-256 / fail-closed
  - role 매트릭스       → owner/admin/viewer 별 endpoint 접근 통제
  - health              → AUTH_ENABLED 무관 무인증 접근
  - 민감정보 노출 방어  → password/hash/Authorization 미노출

테스트 fixture 는 운영 secrets 파일을 절대 건드리지 않는다 — tmp_path 에
synthetic users 파일만 작성한다. 실제 비밀번호는 평문으로 테스트 코드에
나타나지만 hashing 검증용 식별자(예: "pw_owner_demo") 일 뿐 운영 의미가 없다.
"""

from __future__ import annotations

import hashlib
import json
import secrets as _secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── helpers ──────────────────────────────────────────────────────────────


def _salted_hash(password: str) -> str:
    salt = _secrets.token_bytes(16)
    digest = hashlib.sha256(salt + password.encode("utf-8")).hexdigest()
    return f"sha256${salt.hex()}${digest}"


def _users_payload() -> list[dict]:
    """운영 의미 없는 synthetic 사용자 목록. 비밀번호는 식별자 문자열."""
    return [
        {"username": "owner_u", "password_hash": _salted_hash("pw_owner_demo"), "role": "owner", "enabled": True},
        {"username": "admin_u", "password_hash": _salted_hash("pw_admin_demo"), "role": "admin", "enabled": True},
        {"username": "viewer_u", "password_hash": _salted_hash("pw_viewer_demo"), "role": "viewer", "enabled": True},
        {
            "username": "disabled_u",
            "password_hash": _salted_hash("pw_disabled_demo"),
            "role": "owner",
            "enabled": False,
        },
    ]


def _write_users(tmp_path, payload=None) -> str:
    p = tmp_path / "http_users.json"
    p.write_text(
        json.dumps(payload if payload is not None else _users_payload()),
        encoding="utf-8",
    )
    return str(p)


def _enable_auth(monkeypatch, users_path: str | None):
    import ai_orchestrator.core.config as _config

    monkeypatch.setattr(_config, "AUTH_ENABLED", True)
    if users_path is not None:
        from pathlib import Path

        monkeypatch.setattr(_config, "HTTP_USERS_PATH", Path(users_path))


def _disable_auth(monkeypatch):
    import ai_orchestrator.core.config as _config

    monkeypatch.setattr(_config, "AUTH_ENABLED", False)


def _make_local_agent_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.agent_hub.router.root import local_agent_router

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")

    @app.get("/api/v1/health")
    def _health():
        return {"status": "ok"}

    return TestClient(app, raise_server_exceptions=False)


# ── 1. AUTH_ENABLED=False returns dummy owner ────────────────────────────


def test_auth_disabled_returns_dummy_owner(monkeypatch):
    _disable_auth(monkeypatch)
    from tools.gates.auth import get_current_user

    user = get_current_user(credentials=None)
    assert user["actor"] == "system"
    assert user["role"] == "owner"
    assert user["organization_ids"] == ["default-org"]
    assert user["active_organization_id"] == "default-org"


# ── 2. AUTH_ENABLED=True + missing Authorization → 401 ───────────────────


def test_auth_enabled_missing_credentials_returns_401(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get("/api/v1/local-agents")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").lower().startswith("basic")


# ── 3. wrong scheme → 401 ────────────────────────────────────────────────


def test_auth_enabled_wrong_scheme_returns_401(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get(
        "/api/v1/local-agents",
        headers={"Authorization": "Bearer pretend-token"},
    )
    # HTTPBasic with auto_error=False → credentials None for non-Basic schemes
    assert r.status_code == 401


# ── 4. unknown user → 401 ────────────────────────────────────────────────


def test_auth_enabled_unknown_user_returns_401(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get(
        "/api/v1/local-agents",
        auth=("ghost_u", "anything"),
    )
    assert r.status_code == 401


# ── 5. wrong password → 401 ──────────────────────────────────────────────


def test_auth_enabled_wrong_password_returns_401(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get(
        "/api/v1/local-agents",
        auth=("owner_u", "definitely_wrong"),
    )
    assert r.status_code == 401


# ── 6. owner endpoint allowed ────────────────────────────────────────────


def test_auth_enabled_owner_can_register_agent(monkeypatch, tmp_path):
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.clear()
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.post(
        "/api/v1/local-agents/register",
        json={"host": "h", "os_name": "Windows", "version": "0.1"},
        auth=("owner_u", "pw_owner_demo"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_id"]


# ── 7. admin endpoint allowed ────────────────────────────────────────────


def test_auth_enabled_admin_can_register_agent(monkeypatch, tmp_path):
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.clear()
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.post(
        "/api/v1/local-agents/register",
        json={"host": "h", "os_name": "Windows", "version": "0.1"},
        auth=("admin_u", "pw_admin_demo"),
    )
    assert r.status_code == 200, r.text


# ── 8. viewer can read list ──────────────────────────────────────────────


def test_auth_enabled_viewer_can_list_agents(monkeypatch, tmp_path):
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.clear()
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get(
        "/api/v1/local-agents",
        auth=("viewer_u", "pw_viewer_demo"),
    )
    assert r.status_code == 200
    assert "agents" in r.json()


# ── 9. viewer cannot register / create task / approve ────────────────────


def test_auth_enabled_viewer_cannot_register(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.post(
        "/api/v1/local-agents/register",
        json={"host": "h", "os_name": "Windows", "version": "0.1"},
        auth=("viewer_u", "pw_viewer_demo"),
    )
    assert r.status_code == 403


def test_auth_enabled_viewer_cannot_approve(monkeypatch, tmp_path):
    """viewer 가 capture_screenshot 승인 endpoint 시도 시 403."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.clear()
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    # owner 로 task 생성
    rr = client.post(
        "/api/v1/local-agents/register",
        json={"host": "h", "os_name": "Windows", "version": "0.1"},
        auth=("owner_u", "pw_owner_demo"),
    )
    agent_id = rr.json()["agent_id"]
    cap = client.post(
        f"/api/v1/local-agents/{agent_id}/capture-screenshot",
        json={"dry_run": True},
        auth=("owner_u", "pw_owner_demo"),
    )
    task_id = cap.json()["task_id"]
    # viewer 로 approve 시도
    r = client.post(
        f"/api/v1/local-agents/{agent_id}/tasks/{task_id}/approve",
        json={"token_id": "any"},
        auth=("viewer_u", "pw_viewer_demo"),
    )
    assert r.status_code == 403


# ── 10. users file missing → fail-closed ─────────────────────────────────


def test_auth_enabled_missing_users_file_fails_closed(monkeypatch, tmp_path):
    nonexistent = str(tmp_path / "absent" / "http_users.json")
    _enable_auth(monkeypatch, nonexistent)
    client = _make_local_agent_client()
    r = client.get("/api/v1/local-agents", auth=("owner_u", "pw_owner_demo"))
    assert r.status_code == 401, "missing users file 은 fail-closed 401"


# ── 11. malformed users file → fail-closed ───────────────────────────────


def test_auth_enabled_malformed_users_file_fails_closed(monkeypatch, tmp_path):
    bad = tmp_path / "http_users.json"
    bad.write_text("{not valid json", encoding="utf-8")
    _enable_auth(monkeypatch, str(bad))
    client = _make_local_agent_client()
    r = client.get("/api/v1/local-agents", auth=("owner_u", "pw_owner_demo"))
    assert r.status_code == 401


# ── 12. salted SHA-256 verification ──────────────────────────────────────


def test_salted_sha256_verification_round_trip(tmp_path):
    """평문 → _salted_hash → _verify_password 라운드트립."""
    from tools.gates.auth import _verify_password

    h = _salted_hash("hello")
    assert _verify_password("hello", h) is True
    assert _verify_password("HELLO", h) is False
    assert _verify_password("", h) is False
    # 형식 깨진 hash 도 거부
    assert _verify_password("hello", "sha256$onlytwo") is False
    assert _verify_password("hello", "sha256$nothex$nothex") is False


# ── 13. password / Authorization not in logs ─────────────────────────────


def test_auth_failure_does_not_log_password(monkeypatch, tmp_path, caplog):
    import logging

    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    secret_pw = "super-secret-pw-d3adbeef"  # noqa: S105
    with caplog.at_level(logging.DEBUG, logger="tools.gates.auth"):
        client.get("/api/v1/local-agents", auth=("owner_u", secret_pw))
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_pw not in text
    assert "Basic " not in text
    assert "Authorization" not in text


# ── 14. health remains accessible without auth ───────────────────────────


def test_health_unauthenticated_under_auth_enabled(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── 15. disabled user → 401 ──────────────────────────────────────────────


def test_disabled_user_cannot_authenticate(monkeypatch, tmp_path):
    _enable_auth(monkeypatch, _write_users(tmp_path))
    client = _make_local_agent_client()
    r = client.get(
        "/api/v1/local-agents",
        auth=("disabled_u", "pw_disabled_demo"),
    )
    assert r.status_code == 401


# ── 16. AUTH_ENABLED=False 호환: 인증 없이 모든 endpoint owner 동작 ─────


def test_auth_disabled_endpoint_passes_with_no_credentials(monkeypatch):
    """AUTH_ENABLED=False 상태에서 인증 헤더 없어도 owner 권한으로 통과."""
    import ai_orchestrator.agent_hub.registry.facade as reg

    reg.clear()
    _disable_auth(monkeypatch)
    client = _make_local_agent_client()
    r = client.post(
        "/api/v1/local-agents/register",
        json={"host": "h", "os_name": "Windows", "version": "0.1"},
    )
    assert r.status_code == 200
    assert r.json()["agent_id"]
