"""HAEHAN_WHOAMI_ROUTE_01 회귀 테스트."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# FastAPI TestClient 의 lifespan/startup 시 외부 서버 WS 연결 시도가 있을 수 있어
# 가능하면 import 후 module-level state 를 격리해야 함.

@pytest.fixture
def client(monkeypatch):
    """깨끗한 local_server app 으로 TestClient 생성.

    TestClient 의 ASGI client 는 ('testclient', port) 이므로 RemoteAccessMiddleware
    가 is_local=False 로 판정 → 미들웨어 통과를 위해 _remote_enabled / _verify_token
    monkeypatch 로 우회. /api/v1/whoami 응답 자체에는 영향 없음.
    """
    monkeypatch.setattr("desktop.local_server._remote_enabled", lambda: True)
    monkeypatch.setattr("desktop.local_server._verify_token", lambda t: True)
    from fastapi.testclient import TestClient
    from desktop import local_server
    return TestClient(local_server.app)


@pytest.fixture
def reset_role_env():
    """HAEHAN_ROLE env 보존 → 복원."""
    saved = os.environ.pop("HAEHAN_ROLE", None)
    yield
    if saved is None:
        os.environ.pop("HAEHAN_ROLE", None)
    else:
        os.environ["HAEHAN_ROLE"] = saved


# ── 라우터 존재 ────────────────────────────────────────────────────────

def test_whoami_route_exists(client):
    r = client.get("/api/v1/whoami")
    assert r.status_code == 200


def test_whoami_returns_json(client):
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert isinstance(data, dict)


def test_whoami_has_ok_key(client):
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert "ok" in data
    assert data["ok"] is True


def test_whoami_has_role_key(client):
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert "role" in data
    assert isinstance(data["role"], str)


def test_whoami_has_admin_key(client):
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert "admin" in data
    assert isinstance(data["admin"], bool)


def test_whoami_has_source_key(client):
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert "source" in data
    assert data["source"] in ("env", "config", "default", "test")


# ── role → admin 매핑 ─────────────────────────────────────────────────

def test_role_admin_returns_admin_true(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "admin"
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert data["role"] == "admin"
    assert data["admin"] is True


def test_role_owner_returns_admin_true(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "owner"
    r = client.get("/api/v1/whoami")
    data = r.json()
    assert data["role"] == "owner"
    assert data["admin"] is True


def test_role_user_returns_admin_false(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "user"
    data = client.get("/api/v1/whoami").json()
    assert data["role"] == "user"
    assert data["admin"] is False


def test_role_viewer_returns_admin_false(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "viewer"
    data = client.get("/api/v1/whoami").json()
    assert data["admin"] is False


def test_role_any_returns_admin_false(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "any"
    data = client.get("/api/v1/whoami").json()
    assert data["admin"] is False


def test_unknown_role_falls_back_default(client, reset_role_env):
    """KNOWN_ROLES 외 값 → default ('any')."""
    os.environ["HAEHAN_ROLE"] = "superuser"
    data = client.get("/api/v1/whoami").json()
    assert data["role"] == "any"
    assert data["admin"] is False
    assert data["source"] == "default"


def test_env_role_source(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "admin"
    data = client.get("/api/v1/whoami").json()
    assert data["source"] == "env"


def test_default_source_when_no_env(client, reset_role_env):
    """env 없을 때 source=default."""
    data = client.get("/api/v1/whoami").json()
    assert data["source"] in ("default", "config")


# ── secret leak — 응답 키 ──────────────────────────────────────────────

FORBIDDEN_RESPONSE_KEYS = [
    "token", "device_token", "registration_code",
    "bearer", "cookie", "authorization",
    "secret", "password", "api_key",
]


@pytest.mark.parametrize("role", ["admin", "owner", "user", "viewer", "any"])
def test_no_secret_keys_in_response(client, reset_role_env, role):
    os.environ["HAEHAN_ROLE"] = role
    data = client.get("/api/v1/whoami").json()
    body = json.dumps(data).lower()
    for fk in FORBIDDEN_RESPONSE_KEYS:
        assert fk not in body, f"role={role} 응답에 '{fk}' 포함: {data}"


def test_no_sk_prefix_in_response(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "admin"
    body = client.get("/api/v1/whoami").text
    assert "sk-" not in body
    assert "sk_" not in body.lower() or body.lower().count("sk_") == 0


def test_response_keys_are_whitelisted(client, reset_role_env):
    """응답 dict 의 키는 ok/role/admin/source 만 허용."""
    os.environ["HAEHAN_ROLE"] = "admin"
    data = client.get("/api/v1/whoami").json()
    allowed = {"ok", "role", "admin", "source"}
    extra = set(data.keys()) - allowed
    assert not extra, f"비허용 응답 키 등장: {extra}"


# ── local-only bypass 금지 ────────────────────────────────────────────

def test_localhost_does_not_grant_admin_automatically(client, reset_role_env):
    """기본 (env 없음) 시 admin=False — 127.0.0.1 이라는 이유로 admin 자동 부여 금지."""
    # reset_role_env 가 HAEHAN_ROLE 제거
    data = client.get("/api/v1/whoami").json()
    assert data["admin"] is False
    assert data["role"] == "any"


def test_explicit_user_role_not_promoted(client, reset_role_env):
    os.environ["HAEHAN_ROLE"] = "user"
    data = client.get("/api/v1/whoami").json()
    assert data["admin"] is False


# ── admin_webview ↔ whoami 통합 ────────────────────────────────────────

def test_admin_webview_uses_whoami_path():
    """admin_webview 가 /api/v1/whoami 경로를 사용하는지 소스 검사."""
    src = (ROOT / "desktop/admin_webview.py").read_text(encoding="utf-8")
    assert "/api/v1/whoami" in src


def test_admin_webview_passes_with_admin_role(client, reset_role_env):
    from desktop import admin_webview as aw
    os.environ["HAEHAN_ROLE"] = "admin"
    def caller(server_url, timeout):
        return client.get("/api/v1/whoami").json()
    r = aw.check_role_via_api(api_caller=caller)
    assert r.passed is True
    assert r.role == "admin"


def test_admin_webview_passes_with_owner_role(client, reset_role_env):
    from desktop import admin_webview as aw
    os.environ["HAEHAN_ROLE"] = "owner"
    def caller(server_url, timeout):
        return client.get("/api/v1/whoami").json()
    r = aw.check_role_via_api(api_caller=caller)
    assert r.passed is True


def test_admin_webview_rejects_user_role(client, reset_role_env):
    from desktop import admin_webview as aw
    os.environ["HAEHAN_ROLE"] = "user"
    def caller(server_url, timeout):
        return client.get("/api/v1/whoami").json()
    r = aw.check_role_via_api(api_caller=caller)
    assert r.passed is False


def test_admin_webview_rejects_any_role(client, reset_role_env):
    from desktop import admin_webview as aw
    os.environ["HAEHAN_ROLE"] = "any"
    def caller(server_url, timeout):
        return client.get("/api/v1/whoami").json()
    r = aw.check_role_via_api(api_caller=caller)
    assert r.passed is False


# ── 외부에서 secret 키 섞인 응답이 들어와도 거부 ─────────────────────

def test_admin_webview_rejects_response_with_token():
    from desktop import admin_webview as aw
    def malicious_caller(server_url, timeout):
        return {"ok": True, "role": "admin", "admin": True,
                "device_token": "LEAK"}
    r = aw.check_role_via_api(api_caller=malicious_caller)
    assert r.passed is False
    assert "secret" in r.reason.lower() or "forbidden" in r.reason.lower()


def test_admin_webview_rejects_response_with_registration_code():
    from desktop import admin_webview as aw
    def malicious_caller(server_url, timeout):
        return {"role": "owner", "registration_code": "BAD"}
    r = aw.check_role_via_api(api_caller=malicious_caller)
    assert r.passed is False


# ── 네트워크 실패 안전 처리 ────────────────────────────────────────────

def test_admin_webview_handles_connection_refused():
    from desktop import admin_webview as aw
    def broken(server_url, timeout):
        raise ConnectionRefusedError("server down")
    r = aw.check_role_via_api(api_caller=broken)
    assert r.passed is False
    assert "api_error" in r.reason


def test_admin_webview_handles_timeout():
    from desktop import admin_webview as aw
    def slow(server_url, timeout):
        raise TimeoutError("too slow")
    r = aw.check_role_via_api(api_caller=slow)
    assert r.passed is False
    assert "api_error" in r.reason


def test_admin_webview_handles_invalid_response():
    from desktop import admin_webview as aw
    def bad_json(server_url, timeout):
        raise ValueError("not json")
    r = aw.check_role_via_api(api_caller=bad_json)
    assert r.passed is False


# ── 기존 admin_webview lazy import 보존 ────────────────────────────────

def test_admin_webview_lazy_import_preserved():
    """admin_webview import 후에도 webview 모듈 미로드 (lazy 보존)."""
    for mn in list(sys.modules.keys()):
        if mn == "webview" or mn.startswith("webview."):
            del sys.modules[mn]
    for mn in list(sys.modules.keys()):
        if mn == "desktop.admin_webview":
            del sys.modules[mn]
    from desktop import admin_webview  # noqa
    webview_loaded = [m for m in sys.modules.keys()
                      if m == "webview" or m.startswith("webview.")]
    assert not webview_loaded


# ── 기존 tray menu role guard 보존 ─────────────────────────────────────

def test_tray_menu_role_any_no_admin_item_preserved():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="any", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" not in ids


def test_tray_menu_role_admin_has_admin_item_preserved():
    from desktop import tray_runtime as tr
    s = tr.RegistrationStatus(registered=True, server_url="x", agent_id="la-x")
    items = tr.build_tray_menu_items(status=s, role="admin", admin_mode_available=True)
    ids = [it.id for it in items]
    assert "open_admin" in ids


# ── 수정 금지 파일 미수정 ──────────────────────────────────────────────

def test_webview_app_pywebview_not_modified_in_whoami_route_commit():
    """HAEHAN_WHOAMI_ROUTE_01 커밋 자체가 desktop/webview_app_pywebview.py 를
    수정하지 않았음 — 해당 공정의 '수정 금지' 정책 회귀 검증.

    이후 공정 (예: HAEHAN_STASH_SAFE_RESTORE_01) 에서 stash 복원으로
    해당 파일이 변경되더라도 본 검증은 commit history 기준이므로 영향 없음.
    """
    import subprocess
    log = subprocess.run(
        ["git", "log", "--all", "-E",
         "--grep=^feat.haehan.: HAEHAN_WHOAMI_ROUTE_01",
         "-1", "--name-only", "--pretty=format:%H"],
        cwd=ROOT, capture_output=True, text=True, timeout=5,
    )
    lines = [l for l in log.stdout.strip().split("\n") if l.strip()]
    if not lines:
        pytest.skip("HAEHAN_WHOAMI_ROUTE_01 커밋 미발견")
    files = [l.strip().replace("\\", "/") for l in lines[1:]]
    assert "desktop/webview_app_pywebview.py" not in files


def test_tray_app_not_modified_in_whoami_route_commit():
    import subprocess
    log = subprocess.run(
        ["git", "log", "--all", "-E",
         "--grep=^feat.haehan.: HAEHAN_WHOAMI_ROUTE_01",
         "-1", "--name-only", "--pretty=format:%H"],
        cwd=ROOT, capture_output=True, text=True, timeout=5,
    )
    lines = [l for l in log.stdout.strip().split("\n") if l.strip()]
    if not lines:
        pytest.skip("HAEHAN_WHOAMI_ROUTE_01 커밋 미발견")
    files = [l.strip().replace("\\", "/") for l in lines[1:]]
    assert "desktop/tray_app.py" not in files


# ── local_server.py 최소 수정 검증 ─────────────────────────────────────

def test_local_server_whoami_function_exists():
    src = (ROOT / "desktop/local_server.py").read_text(encoding="utf-8")
    assert "async def whoami" in src or "def whoami" in src


def test_local_server_resolve_whoami_role_exists():
    src = (ROOT / "desktop/local_server.py").read_text(encoding="utf-8")
    assert "_resolve_whoami_role" in src


def test_local_server_whoami_known_roles_constant():
    src = (ROOT / "desktop/local_server.py").read_text(encoding="utf-8")
    # any / user / viewer / admin / owner 5종
    assert "_WHOAMI_KNOWN_ROLES" in src or "WHOAMI_KNOWN_ROLES" in src
