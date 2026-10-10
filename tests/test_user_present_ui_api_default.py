from fastapi.testclient import TestClient

from core.agent_runtime.user_present import user_present_ui_server as server
from core.agent_runtime.user_present.user_present_state_store import STATE_WAITING_FOR_USER, UserPresentStateStore


def test_html_ui_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_USER_PRESENT_UI_FALLBACK", raising=False)

    assert server._html_ui_fallback_enabled() is False


def test_root_is_api_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_USER_PRESENT_UI_FALLBACK", raising=False)
    app = server.create_app(UserPresentStateStore())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert response.json()["html_ui_enabled"] is False


def test_confirm_returns_json_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_USER_PRESENT_UI_FALLBACK", raising=False)
    store = UserPresentStateStore()
    store.create_user_present_task({"workflow_run_id": "wf-api-default"})
    store.mark_waiting_for_user("wf-api-default")
    app = server.create_app(store)
    client = TestClient(app)

    response = client.post("/tasks/wf-api-default/confirm")

    assert response.status_code == 200
    assert response.json()["state"] != STATE_WAITING_FOR_USER
    assert response.json()["safe_to_execute"] is False


def test_html_ui_requires_explicit_fallback(monkeypatch):
    monkeypatch.setenv("HAEHAN_USER_PRESENT_UI_FALLBACK", "1")
    app = server.create_app(UserPresentStateStore())
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
