"""execution_limits 확장 정책: task cooldown / user 5min / 야간 차단."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest

from ai_orchestrator.core.models import TaskRequest


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    from ai_orchestrator.core import config as _cfg

    importlib.reload(_cfg)
    from ai_orchestrator.core import execution_limits as el

    importlib.reload(el)
    yield


def _req(task_id="T1", user="operator_u", action="read_file"):
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type=action,
        target="/tmp/x",  # noqa: S108
        description="x",
        requested_by=user,
    )


def test_task_cooldown_blocks_repeat_within_window():
    from ai_orchestrator.core import execution_limits as el

    r = _req("DUP")
    # 정상 실행 기록
    el.record_execution(r.task_id, r.action_type, r.requested_by, status="OK", risk_level="low")
    ok, reason = el.check_task_cooldown(r.task_id, window_sec=60)
    assert not ok and reason == el.BLOCK_TASK_COOLDOWN


def test_task_cooldown_does_not_count_blocked_entries():
    from ai_orchestrator.core import execution_limits as el

    r = _req("BLK")
    el.record_execution(r.task_id, r.action_type, r.requested_by, status="BLOCKED:night_blocked", risk_level="low")
    ok, _ = el.check_task_cooldown(r.task_id, window_sec=60)
    assert ok


def test_user_5min_window_hits_5_times():
    from ai_orchestrator.core import execution_limits as el

    for i in range(5):
        el.record_execution(f"T{i}", "read_file", "u1", status="OK", risk_level="low")
    r = _req("T6", user="u1")
    ok, reason = el.check_user_5min_window(r.requested_by, max_count=5)
    assert not ok and reason == el.BLOCK_USER_5MIN


def test_user_5min_window_counts_by_user_only():
    from ai_orchestrator.core import execution_limits as el

    for i in range(5):
        el.record_execution(f"O{i}", "read_file", "other", status="OK", risk_level="low")
    ok, _ = el.check_user_5min_window("u1", max_count=5)
    assert ok


def test_night_block_kst_range():
    from ai_orchestrator.core import execution_limits as el

    # UTC 16:30 = KST 01:30 (야간)
    ok, reason = el.check_night_block(datetime(2026, 4, 22, 16, 30, tzinfo=UTC))
    assert not ok and reason == el.BLOCK_NIGHT
    # UTC 03:30 = KST 12:30 (주간)
    ok, _ = el.check_night_block(datetime(2026, 4, 22, 3, 30, tzinfo=UTC))
    assert ok
    # UTC 21:00 = KST 06:00 (end exclusive → 허용)
    ok, _ = el.check_night_block(datetime(2026, 4, 22, 21, 0, tzinfo=UTC))
    assert ok
    # UTC 20:59 = KST 05:59 (야간 경계 직전)
    ok, reason = el.check_night_block(datetime(2026, 4, 22, 20, 59, tzinfo=UTC))
    assert not ok and reason == el.BLOCK_NIGHT


def test_check_execution_policy_combines_all(monkeypatch):
    from ai_orchestrator.core import execution_limits as el

    # 낮 시간대로 강제
    class _D(datetime):
        pass

    def fake_now():
        return datetime(2026, 4, 22, 3, 30, tzinfo=UTC)  # KST 12:30

    monkeypatch.setattr(el, "_now", fake_now)
    r = _req("PX", user="uX")
    ok, reason = el.check_execution_policy(r)
    assert ok, reason
    # 중복 기록 후 policy 차단
    el.record_execution(r.task_id, r.action_type, r.requested_by, status="OK", risk_level="low")
    ok, reason = el.check_execution_policy(r)
    assert not ok and reason == el.BLOCK_TASK_COOLDOWN
