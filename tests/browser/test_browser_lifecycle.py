"""CDP Chrome 수명주기 보조 — 세션 이어서 열기(로그인 유지)·옛 탭 정리·정상 종료. 브라우저 없이 가짜 CDP 로 검증한다."""

from __future__ import annotations

import sys
import types

from scripts.browser.session import browser_lifecycle as lc


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


# ── 시작 페이지(홈) ───────────────────────────────────────────


def test_close_stale_tabs_keeps_one_tab_at_the_given_start_url(monkeypatch):
    calls = _fake_http(monkeypatch, [{"id": "yt", "type": "page"}, {"id": "gm", "type": "page"}])
    assert lc.close_stale_tabs(9222, start_url="https://www.google.com/", sleep=lambda _s: None, clock=_Clock()) == 2
    assert ("PUT", "/json/new?https://www.google.com/") in calls  # 시작 탭을 구글 첫 화면으로 만든다
    assert calls.index(("PUT", "/json/new?https://www.google.com/")) < calls.index(("GET", "/json/close/gm"))  # 옛 탭을 닫기 전에 먼저


def test_close_stale_tabs_defaults_to_a_blank_tab(monkeypatch):
    calls = _fake_http(monkeypatch, [{"id": "a", "type": "page"}])
    lc.close_stale_tabs(9222, sleep=lambda _s: None, clock=_Clock())
    assert ("PUT", "/json/new?about:blank") in calls


def test_start_url_only_allows_http_https_or_blank():
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "chrome://settings", "ftp://x/y", "https://a b/", "https://x/\n", ""):
        assert lc._safe_start_url(bad) == lc.BLANK_URL
    assert lc._safe_start_url("https://www.google.com/") == "https://www.google.com/"
    assert lc._safe_start_url("http://127.0.0.1:8777/x") == "http://127.0.0.1:8777/x"
    assert lc._safe_start_url(lc.BLANK_URL) == lc.BLANK_URL


# ── 중앙 정책(CDP_BROWSER_POLICY) ─────────────────────────────


def test_central_policy_is_valid_and_guardrails_are_on():
    """정책의 세 불리언은 끄면 안 된다(로그인 유지·깨끗한 시작이 깨진다) — 끄는 변경은 이 시험이 막는다."""
    from scripts.common.config import CDP_BROWSER_POLICY

    assert lc.validate_policy(CDP_BROWSER_POLICY) == []
    assert all(CDP_BROWSER_POLICY[k] is True for k in lc.POLICY_REQUIRED_TRUE)


def test_validate_policy_reports_each_problem():
    good = {"start_url": "https://www.google.com/", "restore_last_session": True, "clean_start": True, "graceful_stop_first": True, "restore_settle_s": 10.0}
    assert lc.validate_policy(good) == []
    for key in lc.POLICY_REQUIRED_TRUE:
        assert any(key in problem for problem in lc.validate_policy({**good, key: False}))
    assert lc.validate_policy({**good, "start_url": "about:blank"})  # 시작 페이지는 http(s) 주소여야 한다
    assert lc.validate_policy({**good, "start_url": "file:///x"})
    for bad in (0, 61, "10", True, None):
        assert lc.validate_policy({**good, "restore_settle_s": bad})


def test_session_args_follow_the_policy():
    assert lc.session_args({"restore_last_session": True}) == ["--restore-last-session"]
    assert lc.session_args({"restore_last_session": False}) == []
    assert lc.session_args({}) == []


def test_apply_start_policy_cleans_with_the_policy_url_and_settle_time(monkeypatch):
    seen = {}

    def fake_close(port, *, start_url, settle_s, **kw):
        seen.update(port=port, start_url=start_url, settle_s=settle_s)
        return 3

    monkeypatch.setattr(lc, "close_stale_tabs", fake_close)
    policy = {"clean_start": True, "start_url": "https://www.google.com/", "restore_settle_s": 7.5}
    assert lc.apply_start_policy(9222, policy) == 3
    assert seen == {"port": 9222, "start_url": "https://www.google.com/", "settle_s": 7.5}
    seen.clear()
    assert lc.apply_start_policy(9222, {**policy, "clean_start": False}) == 0 and seen == {}  # 꺼져 있으면 정리하지 않는다


def test_stop_browser_skips_the_graceful_step_only_when_the_policy_says_so():
    calls: list[str] = []
    result = lc.stop_browser(
        9222, 1, is_alive=lambda: True, graceful_first=False,
        graceful=lambda port, is_alive: calls.append("graceful") or True,
        polite=lambda pid, is_alive: calls.append("signal") or True,
        force=lambda pid: calls.append("force"),
    )
    assert result == "signal" and calls == ["signal"]  # 정책이 끄면 CDP 단계를 건너뛴다(기본은 켜짐 — 위 시험이 고정)
