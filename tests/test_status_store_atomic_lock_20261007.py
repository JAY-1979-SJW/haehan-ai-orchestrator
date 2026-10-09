"""core/agent_runtime/connection/status_store.py — 원자적 잠금·상태 저장 (T4 R10).

acquire_lock()의 check-then-set 레이스와 write_status()의 비원자적 write_text()를
O_CREAT|O_EXCL + tmp+replace로 고친 것을 확인한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.agent_runtime.connection import status_store as ss


@pytest.fixture(autouse=True)
def _isolated_status_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    status_dir = tmp_path / "local_agent"
    monkeypatch.setattr(ss, "_STATUS_DIR", status_dir)
    monkeypatch.setattr(ss, "_STATUS_FILE", status_dir / "status.json")
    monkeypatch.setattr(ss, "_LOCK_FILE", status_dir / "agent.lock")
    yield


def test_acquire_lock_second_attempt_fails_while_held():
    assert ss.acquire_lock("t1") is True
    assert ss.acquire_lock("t2") is False
    assert ss.lock_task_id() == "t1"


def test_release_then_acquire_succeeds():
    ss.acquire_lock("t1")
    ss.release_lock()
    assert ss.acquire_lock("t2") is True
    assert ss.lock_task_id() == "t2"


def test_write_status_leaves_no_tmp_leftover():
    ss.write_status(running=True, task_id="t1")
    leftover_tmp = list(ss._STATUS_DIR.glob(f"{ss._STATUS_FILE.name}.tmp.*"))
    assert leftover_tmp == []
    assert ss.read_status()["task_id"] == "t1"
