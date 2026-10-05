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
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None, clock=_Clock()) == 2
    assert ("PUT", "/json/new?about:blank") in calls
    assert calls.index(("PUT", "/json/new?about:blank")) < calls.index(("GET", "/json/close/yt"))  # 마지막 탭을 닫으면 Chrome 이 끝나므로 빈 탭을 먼저
    assert [c for c in calls if "/json/close/" in c[1]] == [("GET", "/json/close/gm"), ("GET", "/json/close/yt")]  # 서비스 워커는 닫지 않는다


class _Clock:
    """시험용 시계: 호출할 때마다 0.1초씩 흐른다."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 0.1
        return self.t


def test_close_stale_tabs_waits_until_restored_tab_list_stops_changing(monkeypatch):
    """세션 복원은 탭을 하나씩 늘려 간다 — 고정 대기가 아니라 목록이 두 번 연속 같을 때까지 기다린 뒤 전부 닫는다."""
    snapshots = iter([[{"id": "a", "type": "page"}], [{"id": "a", "type": "page"}, {"id": "b", "type": "page"}, {"id": "c", "type": "page"}]])
    last = {"v": [{"id": "a", "type": "page"}, {"id": "b", "type": "page"}, {"id": "c", "type": "page"}]}
    calls: list[tuple[str, str]] = []

    def fake(port, path, method="GET", timeout=5.0):
        calls.append((method, path))
        if path == "/json/list":
            last["v"] = next(snapshots, last["v"])
            return last["v"]
        return {}

    monkeypatch.setattr(lc, "_http", fake)
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None, clock=_Clock()) == 3  # 첫 목록(1개)만 보고 닫지 않았다
    assert len([c for c in calls if "/json/close/" in c[1]]) == 3


def test_close_stale_tabs_gives_up_waiting_after_the_timeout(monkeypatch):
    counter = iter(range(1, 1000))

    def fake(port, path, method="GET", timeout=5.0):
        if path == "/json/list":
            return [{"id": f"t{next(counter)}", "type": "page"}]  # 매번 다른 탭 = 끝내 안정되지 않는 목록
        return {}

    monkeypatch.setattr(lc, "_http", fake)
    assert lc.close_stale_tabs(9222, settle_s=1.0, sleep=lambda _s: None, clock=_Clock()) >= 1  # 시간이 지나면 그때까지 본 탭을 정리하고 끝낸다


def test_close_stale_tabs_does_nothing_when_no_page_tabs(monkeypatch):
    calls = _fake_http(monkeypatch, [{"id": "sw", "type": "service_worker"}])
    assert lc.close_stale_tabs(9222, sleep=lambda _s: None, clock=_Clock()) == 0
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


# ── 종료 3단계 ────────────────────────────────────────────────


def _stop(**kw):
    log: list[str] = []
    result = lc.stop_browser(
        9222,
        4242,
        is_alive=kw.get("alive", lambda: True),
        graceful=lambda port, is_alive: (log.append("graceful"), kw.get("g", False))[1],
        polite=lambda pid, is_alive: (log.append("signal"), kw.get("s", False))[1],
        force=lambda pid: log.append(f"force:{pid}"),
    )
    return result, log


def test_stop_browser_prefers_graceful_then_signal_then_force():
    assert _stop(g=True) == ("graceful", ["graceful"])  # 앞 단계가 성공하면 뒤 단계는 부르지 않는다
    assert _stop(g=False, s=True) == ("signal", ["graceful", "signal"])
    assert _stop(g=False, s=False) == ("forced", ["graceful", "signal", "force:4242"])  # 강제 종료는 마지막 수단


def test_stop_browser_does_nothing_when_already_stopped():
    assert _stop(alive=lambda: False) == ("already_stopped", [])


def test_polite_signal_never_uses_the_force_option(monkeypatch):
    import os
    import subprocess

    sent: list[object] = []
    monkeypatch.setattr(subprocess, "run", lambda args, **_k: sent.append(list(args)))
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append(("kill", pid, sig)))
    assert lc._polite_signal(4242, is_alive=lambda: False, sleep=lambda _s: None) is True
    assert len(sent) == 1
    flat = [str(x).lower() for x in sent[0]]  # taskkill 인자 목록 또는 ("kill", pid, sig)
    assert "/f" not in flat and "/t" not in flat  # 강제(/F)·프로세스 트리(/T) 종료가 아니다


def test_polite_signal_returns_false_when_browser_ignores_it(monkeypatch):
    import os
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: None)
    monkeypatch.setattr(os, "kill", lambda *_a: None)
    ticks = iter(range(0, 1000))
    assert lc._polite_signal(4242, is_alive=lambda: True, timeout_s=3, sleep=lambda _s: None, clock=lambda: next(ticks)) is False
