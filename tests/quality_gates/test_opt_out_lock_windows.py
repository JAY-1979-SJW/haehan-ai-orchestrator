"""수신거부 잠금(gate_core._opt_out_guard) — Windows 의 삭제 보류 PermissionError 처리.

배경(2026-10-07, PR #156 CI): 다른 프로세스가 방금 unlink 한 잠금 파일은 Windows 에서 '삭제 보류' 상태라 같은 이름을
O_CREAT|O_EXCL 로 만들면 FileExistsError 가 아니라 PermissionError(Errno 13)로 실패한다. 예전 코드는 FileExistsError 만
'잠금 중'으로 처리해 잠금을 기다리지 못하고 프로세스가 죽었다(CI 러너에서 5회 중 1회 재현, run 37611190243).
데이터 유실 위험이 있는 잠금이라 시험을 느슨하게 하거나 재시도·타임아웃으로 가리지 않고 원인(오류 종류)을 직접 주입해 검증한다.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.gates import gate_core as g


@pytest.fixture
def gate_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("GATE_DATA_DIR", str(tmp_path / "gate"))
    return tmp_path / "gate"


def _inject_lock_open_errors(monkeypatch, errors: list[BaseException]):
    """잠금 파일을 만드는 os.open 호출에만 errors 를 차례로 일으키고, 그 뒤와 다른 경로는 실제 os.open 으로 위임한다."""
    real_open = os.open
    pending = list(errors)
    calls = {"lock": 0}

    def fake_open(path, flags, *a, **k):
        if str(path).endswith(".lock") and flags & os.O_EXCL:
            calls["lock"] += 1
            if pending:
                raise pending.pop(0)
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(g.os, "open", fake_open)
    return calls


def test_windows_permission_error_on_lock_create_is_treated_as_busy_and_retried(gate_dir, monkeypatch):
    monkeypatch.setattr(g, "_IS_WINDOWS", True)
    calls = _inject_lock_open_errors(monkeypatch, [PermissionError(13, "Access denied")] * 3)
    g.add_opt_out("Retry@T.com")
    assert calls["lock"] == 4  # 3번 막힌 뒤 4번째에 잠금을 얻었다
    assert g.opt_out_list() == {"retry@t.com"}
    assert not (gate_dir / "opt_out.lock").exists()  # 해제도 정상


def test_windows_persistent_permission_error_is_raised_after_the_deadline_not_swallowed(gate_dir, monkeypatch):
    monkeypatch.setattr(g, "_IS_WINDOWS", True)
    monkeypatch.setattr(g, "_LOCK_WAIT_S", 0.1)
    _inject_lock_open_errors(monkeypatch, [PermissionError(13, "Access denied")] * 10_000)
    with pytest.raises(PermissionError):
        g.add_opt_out("never@t.com")
    assert g.opt_out_list() in (set(), None)  # 쓰지 못했으니 목록에 들어가지 않았다(조용히 가짜 성공하지 않음)


def test_non_windows_permission_error_is_raised_immediately(gate_dir, monkeypatch):
    """POSIX 의 PermissionError 는 진짜 권한 문제 — 기다리지 않고 바로 올린다."""
    monkeypatch.setattr(g, "_IS_WINDOWS", False)
    calls = _inject_lock_open_errors(monkeypatch, [PermissionError(13, "denied")] * 5)
    with pytest.raises(PermissionError):
        g.add_opt_out("x@t.com")
    assert calls["lock"] == 1


class _FlakyLock:
    """unlink 가 처음 몇 번 PermissionError 를 내는 잠금 파일 대역."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0
        self.deleted = False

    def unlink(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise PermissionError(13, "sharing violation")
        self.deleted = True


def test_release_retries_transient_sharing_violation_on_windows(monkeypatch):
    monkeypatch.setattr(g, "_IS_WINDOWS", True)
    lock = _FlakyLock(fail_times=3)
    g._release_lock_file(lock)  # type: ignore[arg-type]
    assert lock.deleted and lock.calls == 4


def test_release_gives_up_with_a_log_instead_of_hanging(monkeypatch, caplog):
    monkeypatch.setattr(g, "_IS_WINDOWS", True)
    monkeypatch.setattr(g, "_UNLINK_RETRY_S", 0.05)
    lock = _FlakyLock(fail_times=10_000)
    with caplog.at_level("WARNING"):
        g._release_lock_file(lock)  # type: ignore[arg-type]
    assert not lock.deleted
    assert any("잠금 파일 삭제 실패" in r.getMessage() for r in caplog.records)


def test_release_ignores_already_missing_lock(tmp_path):
    g._release_lock_file(Path(tmp_path / "missing.lock"))  # 예외 없이 끝난다
