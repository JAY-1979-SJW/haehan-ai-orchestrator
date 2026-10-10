"""GET /api/v1/auth/me endpoint 테스트.

검증 항목:
1. AUTH_ENABLED=False(또는 dependency override) 환경에서 actor/role만 반환
2. 응답에 password·password_hash·token·session·cookie·secret·hash 원문 필드 없음
3. viewer/admin/owner 각각 자기 role 반환
4. require_role을 사용하지 않으므로 모든 인증 성공 사용자가 접근 가능
5. AUTH_ENABLED=True 환경에서 인증 없으면 401

실제 http_users.json secret/hash 값을 사용하지 않으며
테스트 fixture에 실제 비밀번호가 없다. synthetic 값만 사용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

_FORBIDDEN_FIELDS = {
    "password",
    "password_hash",
    "token",
    "session",
    "cookie",
    "secret",
    "hash",
    "salt",
}


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


def _make_client(user_override: dict):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.auth.auth_router import auth_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    _override_current_user(app, get_current_user, user_override)
    return TestClient(app, raise_server_exceptions=True)


# ── 1. actor/role만 반환 (AUTH_ENABLED=False 상당) ───────────────────────────


def test_me_returns_actor_and_role_only():
    """응답 JSON에 actor, role 두 필드만 있어야 한다."""
    client = _make_client({"actor": "system", "role": "owner"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["actor"] == "system"
    assert body["role"] == "owner"
    assert set(body.keys()) == {"actor", "role"}


# ── 2. 금지 필드 없음 ────────────────────────────────────────────────────────


def test_me_does_not_expose_sensitive_fields():
    """password·hash·token·session·cookie·secret 필드가 응답에 없다."""
    client = _make_client({"actor": "system", "role": "owner"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    exposed = _FORBIDDEN_FIELDS & set(body.keys())
    assert not exposed, f"민감 필드가 응답에 노출됨: {exposed}"


# ── 3. viewer role 반환 ───────────────────────────────────────────────────────


def test_me_viewer_role():
    """viewer 사용자는 role=viewer를 반환받는다."""
    client = _make_client({"actor": "viewer_test", "role": "viewer"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "viewer"
    assert body["actor"] == "viewer_test"


# ── 4. admin role 반환 ────────────────────────────────────────────────────────


def test_me_admin_role():
    """admin 사용자는 role=admin을 반환받는다."""
    client = _make_client({"actor": "admin_test", "role": "admin"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "admin"
    assert body["actor"] == "admin_test"


# ── 5. owner role 반환 ────────────────────────────────────────────────────────


def test_me_owner_role():
    """owner 사용자는 role=owner를 반환받는다."""
    client = _make_client({"actor": "owner_test", "role": "owner"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "owner"


# ── 6. AUTH_ENABLED=True 환경 인증 없으면 401 ─────────────────────────────────


def test_me_returns_401_when_auth_enabled_and_no_credentials(monkeypatch):
    """AUTH_ENABLED=True일 때 인증 없이 호출하면 401을 반환한다."""
    import ai_orchestrator.core.config as _config

    # reload 없이 monkeypatch만 사용 — get_current_user는 런타임에 config 값을 읽음
    monkeypatch.setattr(_config, "AUTH_ENABLED", True)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from ai_orchestrator.auth.auth_router import auth_router

    app = FastAPI()
    # dependency_overrides 없이 실제 get_current_user 사용
    app.include_router(auth_router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401, f"인증 없음에도 {r.status_code} 반환"


# ── 7. require_role 사용하지 않음 — 간접 확인 ────────────────────────────────


def test_me_accessible_without_require_role():
    """viewer도 /auth/me에 접근 가능하다 (require_role 미사용 확인)."""
    client = _make_client({"actor": "viewer_only", "role": "viewer"})
    r = client.get("/api/v1/auth/me")
    # viewer가 접근 가능하면 require_role("admin","owner")이 없다는 것을 의미
    assert r.status_code == 200
    assert r.json()["role"] == "viewer"
