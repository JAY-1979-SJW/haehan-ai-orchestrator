"""CDP 데몬 종료 판정 — Chrome 이 닫히면 다시 띄우지 않고 데몬을 끝낸다. 포트가 열린(살아있는) Chrome 은 응답이 느려도 건드리지 않는다."""

from __future__ import annotations

import pytest

from scripts.browser.cdp import cdp_daemon as d


@pytest.mark.parametrize(
    ("streak", "port_open", "expected"),
    [
        (0, False, False),
        (d.CDP_FAIL_THRESHOLD - 1, False, False),  # 아직 임계 전
        (d.CDP_FAIL_THRESHOLD, False, True),  # 포트가 닫힘 = Chrome 이 없다 -> 재기동 없이 데몬 종료
        (d.CDP_FAIL_THRESHOLD, True, False),  # 포트는 열려 있고 응답만 느림 -> 기다린다
        (1000, True, False),  # 아무리 오래 느려도 살아있는 Chrome 은 죽이지 않는다
    ],
)
def test_should_stop_daemon(streak, port_open, expected):
    assert d._should_stop_daemon(streak, port_open) is expected


def test_daemon_has_no_chrome_relaunch_or_archive_monitor():
    assert not hasattr(d, "_restart_chrome")
    assert not hasattr(d, "_should_restart_chrome")
    src = open(d.__file__, encoding="utf-8").read()
    assert '"archive"' not in src


def test_heartbeat_stops_daemon_when_chrome_closed(monkeypatch):
    monkeypatch.setattr(d, "_heartbeat_probe", lambda f, h, _r: (f + 1, 0))
    monkeypatch.setattr(d, "_port_listening", lambda *a, **k: False)
    monkeypatch.setattr(d, "_save_state", lambda *_a, **_k: None)
    monkeypatch.setattr(d, "_restart_dead_monitors", lambda: None)
    monkeypatch.setattr(d, "_launch_chrome", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Chrome must not be relaunched")))
    monkeypatch.setattr(d._stop_event, "wait", lambda timeout=None: False)
    d._stop_event.clear()
    try:
        d._heartbeat_loop()
        assert d._stop_event.is_set()
    finally:
        d._stop_event.clear()


def test_port_listening_false_on_closed_port():
    assert d._port_listening(1, timeout=0.2) is False
