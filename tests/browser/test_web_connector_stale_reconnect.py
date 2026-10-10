"""공유 CDP 연결의 '캐시가 낡아 재연결' 경로 — 이전 Playwright 인스턴스를 먼저 멈춰야 한다.

멈추지 않고 버리면 그 내부 이벤트루프가 전용 브라우저 스레드에 남아 이후의 모든 sync_playwright().start() 가
"Sync API inside the asyncio loop" 로 영구 실패한다(2026-10-04 실측: 사이트 지도 실행이 500). 실제 브라우저·Playwright 를 쓰지 않는다.
"""

from __future__ import annotations

import pytest

from scripts.browser.cdp import connection as wc


class FakePlaywright:
    def __init__(self, log, name, stop_error=None):
        self.log, self.name, self.stop_error = log, name, stop_error
        ctx = object()
        self.chromium = type("C", (), {"connect_over_cdp": lambda _self, _url: self._browser(ctx)})()
        self.ctx = ctx

    def _browser(self, ctx):
        self.log.append(f"connect:{self.name}")
        return type("B", (), {"contexts": [ctx], "is_connected": lambda _s: True})()

    def stop(self):
        self.log.append(f"stop:{self.name}")
        if self.stop_error:
            raise self.stop_error


@pytest.fixture
def stale_state(monkeypatch):
    log: list[str] = []
    old = FakePlaywright(log, "old")
    dead_browser = type("Dead", (), {"is_connected": lambda _s: False})()
    monkeypatch.setattr(wc, "_PLAYWRIGHT_INSTANCE", old)
    monkeypatch.setattr(wc, "_BROWSER_CACHE", dead_browser)
    monkeypatch.setattr(wc, "_BROWSER_CONTEXT_CACHE", object())
    monkeypatch.setattr(wc, "_get_cdp_port", lambda: 9222)

    class Starter:
        def __init__(self, instance):
            self.instance = instance

        def start(self):
            log.append("start:new")
            return self.instance

    new = FakePlaywright(log, "new")
    monkeypatch.setattr(wc, "sync_playwright", lambda: Starter(new))
    return log, old, new


def test_stale_connection_is_stopped_before_reconnecting(stale_state):
    log, _old, new = stale_state
    browser, ctx = wc._connect_browser()
    assert log == ["stop:old", "start:new", "connect:new"]  # 이전 인스턴스를 멈춘 뒤에야 새로 시작한다
    assert ctx is new.ctx and wc._PLAYWRIGHT_INSTANCE is new
    assert browser.is_connected()


def test_stop_failure_of_the_old_instance_does_not_block_reconnecting(stale_state):
    log, old, _new = stale_state
    old.stop_error = RuntimeError("이미 죽은 연결")
    wc._connect_browser()
    assert log == ["stop:old", "start:new", "connect:new"]  # 정리 실패를 삼키고 재연결은 계속한다


def test_healthy_cache_is_reused_without_touching_playwright(monkeypatch):
    log: list[str] = []
    ctx = object()
    alive = type("B", (), {"is_connected": lambda _s: True})()
    monkeypatch.setattr(wc, "_BROWSER_CACHE", alive)
    monkeypatch.setattr(wc, "_BROWSER_CONTEXT_CACHE", ctx)
    monkeypatch.setattr(wc, "_PLAYWRIGHT_INSTANCE", FakePlaywright(log, "live"))
    monkeypatch.setattr(wc, "sync_playwright", lambda: pytest.fail("건강한 연결을 다시 맺으면 안 된다"))
    assert wc._connect_browser() == (alive, ctx)
    assert log == []  # 멈추지도 않는다
