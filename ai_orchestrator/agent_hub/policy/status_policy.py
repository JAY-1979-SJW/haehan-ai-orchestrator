"""로컬 에이전트 태스크 상태 정책.

태스크 상태 상수, 상태 전이 매트릭스, 상태 검증 함수를 중앙화한다.
"""
from __future__ import annotations


# ── 태스크 상태 상수 ────────────────────────────────────────────────────────

# active task 로 간주하는 상태 집합 (cancel_requested 포함 — 아직 agent가 처리 중)
ACTIVE_TASK_STATUSES: frozenset[str] = frozenset({"delivered", "running", "cancel_requested"})

# 취소 가능한 상태 집합
CANCELLABLE_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "waiting_approval", "delivered", "running"
})

# 종료 상태 집합
TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({
    "completed", "failed", "rejected", "cancelled"
})

# 알려진 모든 태스크 상태
KNOWN_TASK_STATUSES: frozenset[str] = frozenset({
    "queued", "delivered", "running",
    "waiting_approval", "completed", "failed", "rejected",
    "cancel_requested", "cancelled",
})


# ── 상태 전이 매트릭스 ───────────────────────────────────────────────────────

# 허용된 상태 전이만 등록. 미등록 전이는 호출자가 차단해야 한다.
# waiting_approval/rejected 는 별도 함수에서만 처리하므로 여기서는 정규 실행 흐름만 포함.
# waiting_approval → cancelled 는 cancel_task() 전용 함수에서만 처리한다.
VALID_TASK_TRANSITIONS: dict[str, set[str]] = {
    "queued":           {"delivered", "failed", "cancelled"},
    "delivered":        {"running", "failed", "cancel_requested"},
    "running":          {"completed", "failed", "cancel_requested"},
    "cancel_requested": {"cancelled", "failed", "completed"},
    "completed":        set(),
    "failed":           set(),
    "cancelled":        set(),
}


# ── 상태 검증 Helper 함수 ────────────────────────────────────────────────────

def can_cancel_task(status: str) -> bool:
    """작업을 취소할 수 있는지 판별.

    취소 가능 상태:
      - queued
      - waiting_approval
      - delivered
      - running

    취소 불가능 상태:
      - completed / failed / rejected / cancelled (종료됨)
      - cancel_requested (이미 취소 요청됨)
    """
    return status in CANCELLABLE_TASK_STATUSES


def is_terminal_status(status: str) -> bool:
    """상태가 종료 상태인지 판별.

    종료 상태:
      - completed
      - failed
      - rejected
      - cancelled
    """
    return status in TERMINAL_TASK_STATUSES
