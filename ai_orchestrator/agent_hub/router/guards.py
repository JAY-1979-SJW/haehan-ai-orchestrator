"""로컬 에이전트 router guard/helper 함수 및 상수.

순수 helper 함수 (side-effect 없음):
  - is_capture_screenshot_task(task) -> bool
  - task_is_dry_run(task) -> bool
  - can_approve_task(task) -> bool
  - can_reject_task(task) -> bool
  - can_cancel_task(status: str) -> bool
  - is_terminal_status(status: str) -> bool

상태 상수:
  - CANCELLABLE_TASK_STATUSES: 취소 가능한 상태 집합
  - TERMINAL_TASK_STATUSES: 종료 상태 집합
"""

from __future__ import annotations

import logging

from ..models import LocalAgentTask

logger = logging.getLogger(__name__)

# ── 상태 상수 ────────────────────────────────────────────────────────────

CANCELLABLE_TASK_STATUSES: frozenset[str] = frozenset({"queued", "waiting_approval", "delivered", "running"})

TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"completed", "failed", "rejected", "cancelled"})


# ── 순수 Helper 함수 ────────────────────────────────────────────────────────


def is_capture_screenshot_task(task: LocalAgentTask | None) -> bool:
    """작업이 capture_screenshot 인지 판별."""
    return bool(task is not None and task.action == "capture_screenshot")


def task_is_dry_run(task: LocalAgentTask | None) -> bool:
    """작업이 dry-run 모드 인지 판별.

    server 는 task.params 를 민감값 제거한 뒤 저장하므로
    options.dry_run 은 보존된다.
    """
    try:
        if task is None:
            return False
        options = task.params.get("options") if isinstance(task.params, dict) else None
        return bool(isinstance(options, dict) and options.get("dry_run"))
    except Exception as exc:  # noqa: BLE001 - task_is_dry_run은 감사로그용 메타데이터 플래그일 뿐 실행을 게이팅하지 않음(호출부는 audit note 기록용) - 예외 시 False 반환해도 실제 승인/차단 로직(can_approve_task 등)에는 영향 없음
        logger.warning("task dry_run 판정 실패: %s", type(exc).__name__)
        return False


def can_approve_task(task: LocalAgentTask | None) -> bool:
    """작업을 승인할 수 있는지 판별.

    승인 가능 조건:
      - status == "waiting_approval"
      - risk_level == "high"
    """
    if task is None:
        return False
    return task.status == "waiting_approval" and task.risk_level == "high"


def can_reject_task(task: LocalAgentTask | None) -> bool:
    """작업을 거절할 수 있는지 판별.

    거절 가능 조건:
      - status == "waiting_approval"
      - risk_level == "high"
    """
    if task is None:
        return False
    return task.status == "waiting_approval" and task.risk_level == "high"


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
