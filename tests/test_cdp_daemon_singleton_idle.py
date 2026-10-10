"""CDP 데몬 단일 인스턴스 락 + 유휴 자동 종료 (2026-10-08 실측 회귀: 다른 worktree 의 데몬이
16:46 부터 상주하며 22:37 Chrome(9222, 8프로세스 705MB)을 재기동 — 메모리 점유 과다).

①단일 인스턴스: 다른(죽지 않은) PID 가 이미 락을 들고 있으면 거부, 죽은 PID 면 재획득 가능.
②유휴 자동 종료: CDP 포트에 외부 연결이 CDP_IDLE_TIMEOUT 초 동안 없으면 _stop_event 를 세운다.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from scripts.browser.cdp import cdp_daemon as d


@pytest.fixture()
def lock_file(tmp_path, monkeypatch):
    p = tmp_path / "cdp_daemon_test.lock"
    monkeypatch.setattr(d, "_SINGLETON_LOCK_FILE", p)
    return p


def test_acquire_lock_succeeds_when_no_lock_exists(lock_file):
    assert d._acquire_singleton_lock() is True
    assert lock_file.exists()
    pid, _ = d._read_singleton_lock()
    assert pid == __import__("os").getpid()


def test_acquire_lock_is_idempotent_for_same_pid(lock_file):
    assert d._acquire_singleton_lock() is True
    assert d._acquire_singleton_lock() is True  # 같은 프로세스가 다시 불러도 거부되면 안 됨


def test_acquire_lock_refuses_when_other_live_pid_holds_it(lock_file, monkeypatch):
    # 실제로 살아 있는 다른 프로세스를 하나 띄워 그 PID 로 락을 선점시킨다.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        lock_file.write_text(f"{proc.pid}\n{datetime.now(UTC).isoformat()}\n", encoding="utf-8")
        assert d._acquire_singleton_lock() is False
        holder = d._singleton_lock_holder()
        assert holder is not None and holder[0] == proc.pid
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_acquire_lock_succeeds_when_holder_pid_is_dead(lock_file):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=10)
    dead_pid = proc.pid
    lock_file.write_text(f"{dead_pid}\n2020-01-01T00:00:00+00:00\n", encoding="utf-8")

    assert d._singleton_lock_holder() is None, "죽은 PID 인데 아직 살아있다고 판정됨"
    assert d._acquire_singleton_lock() is True


def test_release_lock_only_removes_own_pid(lock_file):
    d._acquire_singleton_lock()
    other_pid = d._read_singleton_lock()[0] + 1
    lock_file.write_text(f"{other_pid}\n{datetime.now(UTC).isoformat()}\n", encoding="utf-8")
    d._release_singleton_lock()
    assert lock_file.exists(), "자기 PID 가 아닌 락을 지워버림"


def test_idle_shutdown_triggers_after_timeout(monkeypatch):
    monkeypatch.setattr(d, "CDP_IDLE_TIMEOUT", 60)
    monkeypatch.setattr(d, "_external_cdp_connection_count", lambda *a, **k: 0)
    d._state.last_active_at = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    d._stop_event.clear()

    triggered = d._check_idle_and_maybe_shutdown()

    assert triggered is True
    assert d._stop_event.is_set()


def test_idle_shutdown_does_not_trigger_before_timeout(monkeypatch):
    monkeypatch.setattr(d, "CDP_IDLE_TIMEOUT", 900)
    monkeypatch.setattr(d, "_external_cdp_connection_count", lambda *a, **k: 0)
    d._state.last_active_at = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    d._stop_event.clear()

    assert d._check_idle_and_maybe_shutdown() is False
    assert not d._stop_event.is_set()


def test_idle_timer_resets_when_external_connection_present(monkeypatch):
    monkeypatch.setattr(d, "CDP_IDLE_TIMEOUT", 60)
    monkeypatch.setattr(d, "_external_cdp_connection_count", lambda *a, **k: 1)
    d._state.last_active_at = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    d._stop_event.clear()

    triggered = d._check_idle_and_maybe_shutdown()

    assert triggered is False
    assert not d._stop_event.is_set()
    # last_active_at 가 지금 시각 근처로 갱신돼야 함(유휴 타이머 리셋 증거)
    refreshed = datetime.fromisoformat(d._state.last_active_at)
    assert (datetime.now(UTC) - refreshed).total_seconds() < 5


def test_idle_shutdown_disabled_when_timeout_is_zero(monkeypatch):
    monkeypatch.setattr(d, "CDP_IDLE_TIMEOUT", 0)
    monkeypatch.setattr(d, "_external_cdp_connection_count", lambda *a, **k: 0)
    d._state.last_active_at = "2000-01-01T00:00:00+00:00"
    d._stop_event.clear()

    assert d._check_idle_and_maybe_shutdown() is False
