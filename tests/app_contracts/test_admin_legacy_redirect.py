"""레거시 admin 서버렌더 HTML 라우트의 동작 검증.

- 레거시 비활성(기본): /api/v1/admin/local-agents → admin-web 으로 303 리다이렉트(404 아님).
- 레거시 활성(HAEHAN_ADMIN_LEGACY_UI_FALLBACK): 구 서버렌더 HTML 200.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", raising=False)
    else:
        monkeypatch.setenv("HAEHAN_ADMIN_LEGACY_UI_FALLBACK", flag)
    from ai_orchestrator.routers.admin_ui_router import admin_ui_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(admin_ui_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"actor": "owner-test", "role": "owner"}
    return TestClient(app)


def test_legacy_disabled_redirects_to_admin_web(monkeypatch):
    c = _client(monkeypatch, flag=None)
    r = c.get("/api/v1/admin/local-agents", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/local-agents"  # 2026-09-30 수정: 존재하지 않던 /orchestrator/admin-web 경로 → admin-web 실제 경로


def test_legacy_enabled_returns_html(monkeypatch):
    c = _client(monkeypatch, flag="1")
    r = c.get("/api/v1/admin/local-agents", follow_redirects=False)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
