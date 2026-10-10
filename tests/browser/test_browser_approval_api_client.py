from __future__ import annotations

import json
import urllib.error

from scripts.browser.agent import approval_api_client as client


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_approval_api_not_configured_fails_closed(monkeypatch):
    monkeypatch.delenv("HAEHAN_BROWSER_APPROVAL_API_URL", raising=False)
    monkeypatch.delenv("HAEHAN_APPROVAL_API_URL", raising=False)

    result = client.request_approval_via_api(action="submit", label="test")

    assert result.approved is False
    assert result.status == "api_not_configured"


def test_approval_api_approved(monkeypatch):
    monkeypatch.setenv("HAEHAN_BROWSER_APPROVAL_API_URL", "https://example.test/approval")

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://example.test/approval"
        assert timeout == 3
        body = json.loads(request.data.decode("utf-8"))
        assert body["action"] == "submit"
        assert body["label"] == "민원"
        return _FakeResponse({"approved": True})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    result = client.request_approval_via_api(action="submit", label="민원", timeout=3)

    assert result.approved is True
    assert result.status == "approved"


def test_approval_api_error_fails_closed(monkeypatch):
    monkeypatch.setenv("HAEHAN_BROWSER_APPROVAL_API_URL", "https://example.test/approval")

    def fake_urlopen(_request, timeout):
        assert timeout == client.DEFAULT_TIMEOUT_SECONDS
        raise urllib.error.URLError("down")

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)

    result = client.request_approval_via_api(action="submit", label="test")

    assert result.approved is False
    assert result.status == "api_error"
