from scripts.browser.agent import approval_server


def test_local_ui_fallback_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_LOCAL_APPROVAL_UI_FALLBACK", raising=False)

    assert approval_server._local_ui_fallback_enabled() is False


def test_request_approval_uses_api_by_default(monkeypatch):
    monkeypatch.delenv("HAEHAN_LOCAL_APPROVAL_UI_FALLBACK", raising=False)
    monkeypatch.setattr(approval_server, "ensure_server_running", lambda: (_ for _ in ()).throw(AssertionError("local UI started")))

    class Result:
        approved = True

    def fake_api(**kwargs):
        assert kwargs["action"] == "submit"
        assert kwargs["label"] == "test"
        return Result()

    import scripts.browser.agent.approval_api_client as api_client
    monkeypatch.setattr(api_client, "request_approval_via_api", fake_api)

    assert approval_server.request_approval("submit", "test") is True
