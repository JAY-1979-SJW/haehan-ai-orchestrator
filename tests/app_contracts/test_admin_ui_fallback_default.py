from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(user: dict):
    from ai_orchestrator.routers.admin_ui_router import admin_ui_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(admin_ui_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=True)


def test_legacy_admin_ui_fallback_disabled_by_default(monkeypatch):
    from ai_orchestrator.routers import admin_ui_router

    monkeypatch.delenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", raising=False)

    assert admin_ui_router._legacy_admin_ui_fallback_enabled() is False


def test_legacy_admin_ui_returns_404_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", raising=False)
    client = _client({"actor": "admin_test", "role": "admin"})

    response = client.get("/api/v1/admin/local-agents", follow_redirects=False)

    # 2026-10-04 갱신: 기본 비활성은 404 가 아니라 admin-web 으로 303 안내(admin_ui_router 2026-09-30 동작)
    assert response.status_code == 303
    assert response.headers["location"] == "/local-agents"


def test_legacy_admin_ui_requires_explicit_fallback(monkeypatch):
    monkeypatch.setenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", "1")
    client = _client({"actor": "admin_test", "role": "admin"})

    response = client.get("/api/v1/admin/local-agents")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
