"""CDP 데몬 재시작 판정 — 살아있는(포트가 열린) Chrome 은 응답이 느려도 바로 종료·재시작하지 않는다 (2026-10-05 실측 회귀)."""

from __future__ import annotations

import pytest

from scripts import cdp_daemon as d


@pytest.mark.parametrize(
    ("streak", "port_open", "expected"),
    [
        (0, False, False),
        (d.CDP_FAIL_THRESHOLD - 1, False, False),  # 아직 임계 전
        (d.CDP_FAIL_THRESHOLD, False, True),  # 포트가 닫힘 = Chrome 이 없다 → 재시작
        (d.CDP_FAIL_THRESHOLD, True, False),  # 포트는 열려 있고 응답만 느림 → 기다린다
        (d.CDP_HUNG_THRESHOLD - 1, True, False),
        (d.CDP_HUNG_THRESHOLD, True, True),  # 오래 응답이 없으면 그때는 재시작
    ],
)
def test_should_restart_chrome(streak, port_open, expected):
    assert d._should_restart_chrome(streak, port_open) is expected


def test_hung_threshold_is_longer_than_closed_threshold():
    assert d.CDP_HUNG_THRESHOLD > d.CDP_FAIL_THRESHOLD >= 1


def test_port_listening_false_on_closed_port():
    assert d._port_listening(1, timeout=0.2) is False
