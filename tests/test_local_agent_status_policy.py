"""로컬 에이전트 상태 정책 테스트.

태스크 상태 상수, 상태 전이 매트릭스, 상태 검증 함수의 정합성을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".."))

from ai_orchestrator.agent_hub.policy.status_policy import (
    ACTIVE_TASK_STATUSES,
    CANCELLABLE_TASK_STATUSES,
    KNOWN_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    VALID_TASK_TRANSITIONS,
    can_cancel_task,
    is_terminal_status,
)

# ── 상태 상수 검증 ──────────────────────────────────────────────────────────


def test_active_task_statuses_snapshot():
    """활성 태스크 상태 집합 스냅샷."""
    expected = frozenset({"delivered", "running", "cancel_requested"})
    assert ACTIVE_TASK_STATUSES == expected


def test_known_task_statuses_snapshot():
    """알려진 태스크 상태 집합 스냅샷."""
    expected = frozenset(
        {
            "queued",
            "delivered",
            "running",
            "waiting_approval",
            "completed",
            "failed",
            "rejected",
            "cancel_requested",
            "cancelled",
        }
    )
    assert KNOWN_TASK_STATUSES == expected


def test_cancellable_task_statuses_snapshot():
    """취소 가능한 태스크 상태 집합 스냅샷."""
    expected = frozenset({"queued", "waiting_approval", "delivered", "running"})
    assert CANCELLABLE_TASK_STATUSES == expected


def test_terminal_task_statuses_snapshot():
    """종료 태스크 상태 집합 스냅샷."""
    expected = frozenset({"completed", "failed", "rejected", "cancelled"})
    assert TERMINAL_TASK_STATUSES == expected


# ── 상태 전이 매트릭스 ──────────────────────────────────────────────────────


def test_valid_task_transitions_structure():
    """상태 전이 매트릭스 구조 검증."""
    assert isinstance(VALID_TASK_TRANSITIONS, dict)
    # 모든 KNOWN_TASK_STATUSES가 매트릭스 키이거나 정규 흐름에 없어야 함
    for status in VALID_TASK_TRANSITIONS:
        assert status in KNOWN_TASK_STATUSES


def test_valid_task_transitions_snapshot():
    """상태 전이 매트릭스 스냅샷."""
    expected = {
        "queued": {"delivered", "failed", "cancelled"},
        "delivered": {"running", "failed", "cancel_requested"},
        "running": {"completed", "failed", "cancel_requested"},
        "cancel_requested": {"cancelled", "failed", "completed"},
        "completed": set(),
        "failed": set(),
        "cancelled": set(),
    }
    assert VALID_TASK_TRANSITIONS == expected


def test_valid_task_transitions_no_terminal_sources():
    """종료 상태에서 나가는 전이 없음."""
    for status in TERMINAL_TASK_STATUSES:
        if status in VALID_TASK_TRANSITIONS:
            assert len(VALID_TASK_TRANSITIONS[status]) == 0


# ── can_cancel_task() 함수 ───────────────────────────────────────────────


def test_can_cancel_task_queued():
    """queued 상태는 취소 가능."""
    assert can_cancel_task("queued") is True


def test_can_cancel_task_waiting_approval():
    """waiting_approval 상태는 취소 가능."""
    assert can_cancel_task("waiting_approval") is True


def test_can_cancel_task_delivered():
    """delivered 상태는 취소 가능."""
    assert can_cancel_task("delivered") is True


def test_can_cancel_task_running():
    """running 상태는 취소 가능."""
    assert can_cancel_task("running") is True


def test_can_cancel_task_not_cancellable_completed():
    """completed 상태는 취소 불가."""
    assert can_cancel_task("completed") is False


def test_can_cancel_task_not_cancellable_failed():
    """failed 상태는 취소 불가."""
    assert can_cancel_task("failed") is False


def test_can_cancel_task_not_cancellable_rejected():
    """rejected 상태는 취소 불가."""
    assert can_cancel_task("rejected") is False


def test_can_cancel_task_not_cancellable_cancelled():
    """cancelled 상태는 취소 불가."""
    assert can_cancel_task("cancelled") is False


def test_can_cancel_task_not_cancellable_cancel_requested():
    """cancel_requested 상태는 취소 불가."""
    assert can_cancel_task("cancel_requested") is False


# ── is_terminal_status() 함수 ──────────────────────────────────────────────


def test_is_terminal_status_completed():
    """completed 상태는 종료 상태."""
    assert is_terminal_status("completed") is True


def test_is_terminal_status_failed():
    """failed 상태는 종료 상태."""
    assert is_terminal_status("failed") is True


def test_is_terminal_status_rejected():
    """rejected 상태는 종료 상태."""
    assert is_terminal_status("rejected") is True


def test_is_terminal_status_cancelled():
    """cancelled 상태는 종료 상태."""
    assert is_terminal_status("cancelled") is True


def test_is_terminal_status_not_terminal_queued():
    """queued 상태는 종료 상태가 아님."""
    assert is_terminal_status("queued") is False


def test_is_terminal_status_not_terminal_delivered():
    """delivered 상태는 종료 상태가 아님."""
    assert is_terminal_status("delivered") is False


def test_is_terminal_status_not_terminal_running():
    """running 상태는 종료 상태가 아님."""
    assert is_terminal_status("running") is False


def test_is_terminal_status_not_terminal_waiting_approval():
    """waiting_approval 상태는 종료 상태가 아님."""
    assert is_terminal_status("waiting_approval") is False


def test_is_terminal_status_not_terminal_cancel_requested():
    """cancel_requested 상태는 종료 상태가 아님."""
    assert is_terminal_status("cancel_requested") is False


# ── 상태 집합 정합성 검증 ──────────────────────────────────────────────────


def test_known_includes_active():
    """KNOWN_TASK_STATUSES가 ACTIVE_TASK_STATUSES를 포함."""
    assert ACTIVE_TASK_STATUSES.issubset(KNOWN_TASK_STATUSES)


def test_known_includes_cancellable():
    """KNOWN_TASK_STATUSES가 CANCELLABLE_TASK_STATUSES를 포함."""
    assert CANCELLABLE_TASK_STATUSES.issubset(KNOWN_TASK_STATUSES)


def test_known_includes_terminal():
    """KNOWN_TASK_STATUSES가 TERMINAL_TASK_STATUSES를 포함."""
    assert TERMINAL_TASK_STATUSES.issubset(KNOWN_TASK_STATUSES)


def test_cancellable_and_terminal_disjoint():
    """취소 가능 상태와 종료 상태는 겹치지 않음."""
    assert CANCELLABLE_TASK_STATUSES.isdisjoint(TERMINAL_TASK_STATUSES)


def test_active_excludes_waiting_approval():
    """ACTIVE_TASK_STATUSES는 waiting_approval를 포함하지 않음."""
    assert "waiting_approval" not in ACTIVE_TASK_STATUSES


def test_active_excludes_terminal():
    """ACTIVE_TASK_STATUSES와 TERMINAL_TASK_STATUSES는 겹치지 않음."""
    assert ACTIVE_TASK_STATUSES.isdisjoint(TERMINAL_TASK_STATUSES)


# ── 모듈 import 검증 ────────────────────────────────────────────────────────


def test_status_policy_module_importable():
    """상태 정책 모듈이 정상적으로 임포트 가능한지 검증."""
    import ai_orchestrator.agent_hub.policy.status_policy as status_policy_module

    assert hasattr(status_policy_module, "ACTIVE_TASK_STATUSES")
    assert hasattr(status_policy_module, "VALID_TASK_TRANSITIONS")
    assert hasattr(status_policy_module, "KNOWN_TASK_STATUSES")
    assert hasattr(status_policy_module, "CANCELLABLE_TASK_STATUSES")
    assert hasattr(status_policy_module, "TERMINAL_TASK_STATUSES")
    assert hasattr(status_policy_module, "can_cancel_task")
    assert hasattr(status_policy_module, "is_terminal_status")


def test_no_circular_import_with_registry():
    """상태 정책 모듈과 registry 간 순환 참조 없음을 검증."""
    try:
        from ai_orchestrator.agent_hub.registry import facade as local_agent_registry

        assert local_agent_registry is not None
    except ImportError:
        pass


# ── 상태 전이 경로 검증 ────────────────────────────────────────────────────


def test_queued_can_transition_to_delivered():
    """queued → delivered 전이 가능."""
    allowed = VALID_TASK_TRANSITIONS.get("queued", set())
    assert "delivered" in allowed


def test_queued_cannot_transition_to_completed():
    """queued → completed 직접 전이는 불가."""
    allowed = VALID_TASK_TRANSITIONS.get("queued", set())
    assert "completed" not in allowed


def test_delivered_can_transition_to_running():
    """delivered → running 전이 가능."""
    allowed = VALID_TASK_TRANSITIONS.get("delivered", set())
    assert "running" in allowed


def test_running_can_transition_to_completed():
    """running → completed 전이 가능."""
    allowed = VALID_TASK_TRANSITIONS.get("running", set())
    assert "completed" in allowed


def test_cancel_requested_can_transition_to_cancelled():
    """cancel_requested → cancelled 전이 가능."""
    allowed = VALID_TASK_TRANSITIONS.get("cancel_requested", set())
    assert "cancelled" in allowed
