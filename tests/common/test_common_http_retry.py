"""scripts/common/http_retry.py — 죽은 로컬 프록시 우회 공용 함수 시험."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from scripts.common import http_retry, youtube_http_client
from scripts.google.youtube import search_common

_PROXY_KEYS = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy")


def _clear_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PROXY_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    "reason", ["[WinError 10061] refused", "Connection refused", "대상 컴퓨터에서 연결을 거부했으므로"]
)
def test_retry_when_dead_local_proxy_refused(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    _clear_proxies(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    assert http_retry.should_retry_without_proxy(urllib.error.URLError(reason)) is True


def test_no_retry_without_dead_proxy_or_other_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxies(monkeypatch)
    assert http_retry.should_retry_without_proxy(urllib.error.URLError("Connection refused")) is False
    monkeypatch.setenv("http_proxy", "http://localhost:9")
    assert http_retry.should_retry_without_proxy(urllib.error.URLError("timed out")) is False


def test_urlopen_falls_back_to_no_proxy_opener(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxies(monkeypatch)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        calls.append("direct")
        raise urllib.error.URLError("Connection refused")

    class FakeOpener:
        def open(self, request, timeout):
            calls.append(f"no-proxy:{timeout}")
            return "ok"

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: FakeOpener())
    req = urllib.request.Request("http://example.invalid/")
    assert http_retry.urlopen_with_dead_proxy_fallback(req, timeout=7) == "ok"
    assert calls == ["direct", "no-proxy:7"]


def test_urlopen_reraises_when_not_dead_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_proxies(monkeypatch)

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(urllib.error.URLError):
        http_retry.urlopen_with_dead_proxy_fallback(urllib.request.Request("http://example.invalid/"), timeout=1)


def test_tool_modules_reexport_shared_function() -> None:
    assert youtube_http_client.urlopen_with_dead_proxy_fallback is http_retry.urlopen_with_dead_proxy_fallback
    assert search_common._urlopen_with_dead_proxy_fallback is http_retry.urlopen_with_dead_proxy_fallback
