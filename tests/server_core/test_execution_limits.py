import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".." / ".."))

from ai_orchestrator.core.config import EXECUTION_HISTORY_PATH
from ai_orchestrator.core.execution_limits import (
    BLOCK_RATE_ACTION,
    BLOCK_RATE_USER,
    BLOCK_TIMEOUT,
    current_limits,
)
from ai_orchestrator.core.models import ExecutionPlan, TaskRequest
from ai_orchestrator.tasks.executor import execute


def _cleanup_history():
    if EXECUTION_HISTORY_PATH.exists():
        EXECUTION_HISTORY_PATH.unlink()


def _req(task_id: str, action: str = "read_file", user: str = "test") -> TaskRequest:
    return TaskRequest(
        task_id=task_id,
        source="manual",
        action_type=action,
        target="/tmp/x.log",  # noqa: S108
        description="limit test",
        requested_by=user,
    )


def _plan(task_id: str) -> ExecutionPlan:
    return ExecutionPlan(task_id=task_id, allowed=True, requires_approval=False, steps=[], blocked_reasons=[])


# ── 0. 정상 허용: DRY_RUN_ONLY ────────────────────────────────────
def test_allow_ok():
    _cleanup_history()
    r = _req(f"OK-{uuid.uuid4().hex[:6]}")
    result = execute(_plan(r.task_id), req=r, risk_level="low")
    assert result == "DRY_RUN_ONLY", f"expected DRY_RUN_ONLY, got {result}"
    assert EXECUTION_HISTORY_PATH.exists(), "history not recorded"


# ── 1. action_type 기준 rate limit ───────────────────────────────
def test_rate_limit_action():
    _cleanup_history()
    action = f"read_action_{uuid.uuid4().hex[:6]}"
    max_n = current_limits()["action_max"]
    results = []
    # 서로 다른 사용자로 호출 → user limit 회피, action limit 만 유도
    for i in range(max_n + 1):
        r = _req(f"ACT-{i}", action=action, user=f"user-act-{i}")
        results.append(execute(_plan(r.task_id), req=r, risk_level="low"))
    assert results[:max_n] == ["DRY_RUN_ONLY"] * max_n, results
    assert results[max_n] == f"BLOCKED:{BLOCK_RATE_ACTION}", results


# ── 2. requested_by 기준 rate limit ───────────────────────────────
def test_rate_limit_user():
    _cleanup_history()
    user = f"user-u-{uuid.uuid4().hex[:6]}"
    max_n = current_limits()["user_max"]
    results = []
    # 서로 다른 action 으로 호출 → action limit 회피, user limit 만 유도
    for i in range(max_n + 1):
        r = _req(f"USR-{i}", action=f"read_u_{i}", user=user)
        results.append(execute(_plan(r.task_id), req=r, risk_level="low"))
    assert results[:max_n] == ["DRY_RUN_ONLY"] * max_n, results
    assert results[max_n] == f"BLOCKED:{BLOCK_RATE_USER}", results


# ── 3. timeout ────────────────────────────────────────────────────
def test_timeout():
    _cleanup_history()
    r = _req(f"TO-{uuid.uuid4().hex[:6]}", action="read_slow", user="user-timeout")

    def slow_worker(req):
        time.sleep(5)
        return "DRY_RUN_ONLY"

    result = execute(_plan(r.task_id), req=r, risk_level="low", worker=slow_worker, timeout_sec=1)
    assert result == f"BLOCKED:{BLOCK_TIMEOUT}", result


# ── 4. BLOCKED 엔트리는 rate 카운트에서 제외 ──────────────────────
def test_blocked_entries_not_counted():
    _cleanup_history()
    # 먼저 timeout 유도로 BLOCKED 엔트리 생성 (카운트 되면 안 됨)
    r_to = _req("CNT-TO", action="shared_act", user="shared-user")

    def slow(req):
        time.sleep(2)
        return "DRY_RUN_ONLY"

    execute(_plan(r_to.task_id), req=r_to, risk_level="low", worker=slow, timeout_sec=1)
    # 이어서 정상 호출 max 회 — 모두 허용되어야 함
    max_n = current_limits()["user_max"]
    for i in range(max_n):
        r = _req(f"CNT-{i}", action=f"shared_act_ok_{i}", user="shared-user")
        result = execute(_plan(r.task_id), req=r, risk_level="low")
        assert result == "DRY_RUN_ONLY", (i, result)


# ── 5. 기존 호출(execute(plan) 단독) 회귀 — 리밋 미적용 ───────────
def test_legacy_signature_regression():
    _cleanup_history()
    # req/risk_level 없이 호출 → 기존 DRY_RUN_ONLY 그대로, 기록도 없어야 함
    for i in range(current_limits()["action_max"] + 2):
        result = execute(_plan(f"LEG-{i}"))
        assert result == "DRY_RUN_ONLY"


# ── 6. plan.allowed=False → BLOCKED, 히스토리 미기록 ──────────────
def test_disallowed_plan_unchanged():
    _cleanup_history()
    ep = ExecutionPlan(task_id="NO-1", allowed=False, requires_approval=False, steps=[], blocked_reasons=["policy"])
    result = execute(ep, req=_req("NO-1"), risk_level="low")
    assert result.startswith("BLOCKED:")
    assert "policy" in result


if __name__ == "__main__":
    tests = [
        test_allow_ok,
        test_rate_limit_action,
        test_rate_limit_user,
        test_timeout,
        test_blocked_entries_not_counted,
        test_legacy_signature_regression,
        test_disallowed_plan_unchanged,
    ]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print("\n모든 execution_limits 테스트 통과")
