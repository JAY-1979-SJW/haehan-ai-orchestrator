from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.youtube.oauth_router import youtube_oauth_router


def test_youtube_oauth_callback_route_redacts_code(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_CALLBACK_EXCHANGE_ENABLED", raising=False)
    app = FastAPI()
    app.include_router(youtube_oauth_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/oauth/youtube/callback?code=secret-code&state=state-1")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "waiting_server_exchange_enabled"
    assert data["code_received"] is True
    assert data["code_output"] == "redacted"
    assert "secret-code" not in response.text


def test_youtube_oauth_callback_route_handles_error_without_code():
    app = FastAPI()
    app.include_router(youtube_oauth_router, prefix="/api/v1")
    client = TestClient(app)

    response = client.get("/api/v1/oauth/youtube/callback?error=access_denied")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["reason"] == "google_oauth_error"
    assert data["code_output"] == "redacted"
