import pytest

from core.agent_runtime.browser.cdp_attach import (
    CDPAttachValidationError,
    build_cdp_list_url,
    build_cdp_version_url,
    normalize_cdp_endpoint,
    probe_cdp_endpoint,
    summarize_cdp_tabs,
    summarize_cdp_version,
)


def test_normalize_cdp_endpoint_accepts_loopback_only():
    assert normalize_cdp_endpoint("127.0.0.1", 9222).base_url == "http://127.0.0.1:9222"
    assert normalize_cdp_endpoint("localhost", "9223").base_url == "http://localhost:9223"
    assert normalize_cdp_endpoint("::1", 9224).base_url == "http://[::1]:9224"

    with pytest.raises(CDPAttachValidationError):
        normalize_cdp_endpoint("192.168.1.10", 9222)
    with pytest.raises(CDPAttachValidationError):
        normalize_cdp_endpoint("example.com", 9222)
    with pytest.raises(CDPAttachValidationError):
        normalize_cdp_endpoint("127.0.0.1", 70000)


def test_build_cdp_urls_are_discovery_only():
    assert build_cdp_version_url("127.0.0.1", 9222) == "http://127.0.0.1:9222/json/version"
    assert build_cdp_list_url("localhost", 9222) == "http://localhost:9222/json/list"


def test_summarize_cdp_version_omits_websocket_and_user_agent():
    summary = summarize_cdp_version(
        {
            "Browser": "Chrome/120",
            "Protocol-Version": "1.3",
            "User-Agent": "secret user agent",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/id",
        }
    )

    assert summary == {"Browser": "Chrome/120", "Protocol-Version": "1.3"}


def test_summarize_cdp_tabs_redacts_query_fragment_credentials_and_websocket():
    summary = summarize_cdp_tabs(
        [
            {
                "type": "page",
                "title": "Private Tab",
                "url": "https://user:pass@example.com/path?token=abc#frag",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/id",
            },
            {"type": "worker", "title": "Ignored", "url": "https://example.com/worker"},
        ]
    )
    rendered = str(summary)

    assert summary["tab_count"] == 1
    assert summary["tabs"][0]["url"]["origin"] == "https://example.com"
    assert summary["tabs"][0]["url"]["has_query"] is True
    assert summary["tabs"][0]["url"]["has_fragment"] is True
    assert summary["tabs"][0]["url"]["has_credentials"] is True
    assert "token=abc" not in rendered
    assert "user:pass" not in rendered
    assert "webSocketDebuggerUrl" not in rendered
    assert "ws://" not in rendered


def test_probe_cdp_endpoint_uses_injected_fetcher_and_redacts():
    calls = []

    def fake_fetch(url, timeout):
        calls.append((url, timeout))
        if url.endswith("/json/version"):
            return {"Browser": "Chrome/120", "Protocol-Version": "1.3", "webSocketDebuggerUrl": "ws://hidden"}
        return [
            {
                "type": "page",
                "title": "Example",
                "url": "https://example.com/path?secret=value",
                "webSocketDebuggerUrl": "ws://hidden",
            }
        ]

    result = probe_cdp_endpoint("127.0.0.1", 9222, timeout=0.1, fetch_json=fake_fetch)
    rendered = str(result)

    assert result["available"] is True
    assert calls == [
        ("http://127.0.0.1:9222/json/version", 0.1),
        ("http://127.0.0.1:9222/json/list", 0.1),
    ]
    assert "secret=value" not in rendered
    assert "ws://hidden" not in rendered


def test_probe_cdp_endpoint_rejects_remote_host_before_fetch():
    def fake_fetch(url, timeout):
        raise AssertionError("fetch should not be called")

    with pytest.raises(CDPAttachValidationError):
        probe_cdp_endpoint("10.0.0.2", 9222, fetch_json=fake_fetch)
