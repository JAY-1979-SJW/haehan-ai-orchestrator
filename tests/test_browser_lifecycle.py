"""CDP Chrome 수명주기 보조 — 세션 이어서 열기(로그인 유지)·옛 탭 정리·정상 종료. 브라우저 없이 가짜 CDP 로 검증한다."""

from __future__ import annotations

import sys
import types

from scripts import browser_lifecycle as lc


def test_restore_switch_is_the_bare_chrome_switch():
    """값을 붙이면 안 된다 — 이 스위치는 있기만 하면 켜진다(`=false` 도 켜짐). 실제 Chrome 비교에서 이 형태만 로그인 쿠키를 유지했다."""
    assert lc.RESTORE_SWITCH == "--restore-last-session" and "=" not in lc.RESTORE_SWITCH


def test_page_tab_ids_keeps_only_page_tabs():
    tabs = [
        {"id": "a", "type": "page"},
        {"id": "b", "type": "service_worker"},
        {"id": "c", "type": "browser_ui"},
        {"type": "page"},
        {"id": "d", "type": "page"},
    ]
    assert lc.page_tab_ids(tabs) == ["a", "d"]


def _fake_http(monkeypatch, tabs, *, fail_on=None):
    calls: list[tuple[str, str]] = []

    def fake(port, path, method="GET", timeout=5.0):
        calls.append((method, path))
        if fail_on and fail_on in path:
            raise OSError("x")
        return tabs if path == "/json/list" else {}

    monkeypatch.setattr(lc, "_http", fake)
    return calls


def test_close_stale_tabs_opens_blank_first_then_closes_every_old_page_tab(monkeypatch):
    tabs = [{"id": "yt", "type": "page"}, {"id": "gm", "type": "page"}, {"id": "sw", "type": "service_worker"}]
    calls = _fake_http(monkeypatch, tabs)
    slept = []
    assert lc.close_stale_tabs(9222, sleep=slept.append) == 2
    assert slept == [lc.RESTORE_SETTLE_S]  # 복원이 끝나기를 기다린다
    assert calls[1] == ("PUT", "/json/new?about:blank")  # 마지막 탭을 닫으면 Chrome 이 끝나므로 빈 탭을 먼저
    assert [c for c in calls if "/json/close/" in c[1]] == [
        ("GET", "/json/close/yt"),
        ("GET", "/json/close/gm"),
    ]  # 서비스 워커는 닫지 않는다


def test_close_stale_tabs_does_nothing_when_no_page_tabs(monkeypatch):
    calls = _fake_http(monkeypatch, [{"id": "sw", "type": "service_worker"}])
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None) == 0
    assert all("/json/new" not in c[1] for c in calls)


def test_close_stale_tabs_never_raises(monkeypatch):
    _fake_http(monkeypatch, [], fail_on="/json/list")
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None) == 0  # 브라우저 시작을 막지 않는다
    _fake_http(monkeypatch, [{"id": "a", "type": "page"}], fail_on="/json/close/")
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None) == 0  # 일부 탭 닫기 실패도 예외 없이


class _FakeWS:
    sent: list[str] = []

    def send(self, msg):
        _FakeWS.sent.append(msg)

    def close(self):
        pass


def _install_fake_websocket(monkeypatch):
    _FakeWS.sent = []
    fake = types.SimpleNamespace(create_connection=lambda url, timeout=3: _FakeWS())
    monkeypatch.setitem(sys.modules, "websocket", fake)


def test_graceful_close_sends_browser_close_and_waits_for_exit(monkeypatch):
    _install_fake_websocket(monkeypatch)
    monkeypatch.setattr(lc, "_http", lambda *_a, **_k: {"webSocketDebuggerUrl": "ws://x"})
    alive = iter([True, True, False])
    assert lc.graceful_close(9222, is_alive=lambda: next(alive), sleep=lambda _s: None) is True
    assert '"Browser.close"' in _FakeWS.sent[0]


def test_graceful_close_returns_false_when_browser_never_exits(monkeypatch):
    _install_fake_websocket(monkeypatch)
    monkeypatch.setattr(lc, "_http", lambda *_a, **_k: {"webSocketDebuggerUrl": "ws://x"})
    ticks = iter(range(0, 1000))
    assert (
        lc.graceful_close(9222, is_alive=lambda: True, timeout_s=3, sleep=lambda _s: None, clock=lambda: next(ticks))
        is False
    )  # 호출자가 강제 종료로 넘어간다


def test_graceful_close_returns_false_without_endpoint(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("포트 닫힘")

    monkeypatch.setattr(lc, "_http", boom)
    assert lc.graceful_close(9222, is_alive=lambda: True) is False  # 멈췄거나 이미 없는 브라우저는 기다리지 않는다
    monkeypatch.setattr(lc, "_http", lambda *_a, **_k: {})
    assert lc.graceful_close(9222, is_alive=lambda: True) is False
