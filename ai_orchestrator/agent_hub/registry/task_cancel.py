"""Task cancellation engine."""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import LocalAgentTask
from .common import (
    _ensure_task_transition,
    _lock,
    _tasks,
)


class CancelNotAllowedError(ValueError):
    """이미 종결된 또는 재취소 불가 상태에서 취소를 시도할 때."""


_CANCEL_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "completed",
        "failed",
        "rejected",
        "cancelled",
    }
)

_CANCEL_REASON_MAX_LEN = 200


def cancel_task(
    agent_id: str,
    task_id: str,
    *,
    actor: str = "",
    reason: str = "",
    now: datetime | None = None,
) -> tuple[LocalAgentTask, str]:
    """task 취소 엔진. 상태에 따라 즉시 cancelled 또는 cancel_requested 로 전환.

    반환: (task, action_str)
      - action_str = "cancelled"        (queued / waiting_approval)
      - action_str = "cancel_requested" (delivered / running)

    예외:
      - ValueError: task 없음, agent_id 불일치, reason 초과
      - CancelNotAllowedError: terminal 상태 또는 cancel_requested 재취소
    """
    if reason and len(reason) > _CANCEL_REASON_MAX_LEN:
        raise ValueError(f"reason 이 최대 길이({_CANCEL_REASON_MAX_LEN}자)를 초과합니다")

    now_dt = now if now is not None else datetime.now(UTC)
    now_iso = now_dt.isoformat()
    safe_reason = (reason or "")[:_CANCEL_REASON_MAX_LEN]
    safe_actor = (actor or "")[:80]

    with _lock:
        t = _tasks.get(task_id)
        if t is None or t.agent_id != agent_id:
            raise ValueError(f"task 없음 또는 agent_id 불일치: {agent_id}/{task_id}")

        if t.status in _CANCEL_TERMINAL_STATUSES:
            raise CancelNotAllowedError(f"취소 불가 — 이미 종결된 상태: {t.status!r} (task_id={task_id})")

        if t.status == "cancel_requested":
            raise CancelNotAllowedError(f"취소 불가 — 이미 cancel_requested 상태 (task_id={task_id})")

        if t.status in ("queued", "waiting_approval"):
            # agent에 아직 전달되지 않음 → 즉시 cancelled
            _ensure_task_transition(t, "cancelled") if t.status == "queued" else None
            t.status = "cancelled"
            t.cancel_reason = safe_reason
            t.cancel_requested_by = safe_actor
            t.cancelled_at = now_iso
            t.completed_at = now_iso
            t.updated_at = now_iso
            return t, "cancelled"

        if t.status in ("delivered", "running"):
            # agent에 전달됐거나 실행 중 → cancel_requested
            _ensure_task_transition(t, "cancel_requested")
            t.status = "cancel_requested"
            t.cancel_reason = safe_reason
            t.cancel_requested_by = safe_actor
            t.cancel_requested_at = now_iso
            t.updated_at = now_iso
            return t, "cancel_requested"

        raise CancelNotAllowedError(f"취소 불가 — 처리되지 않은 상태: {t.status!r} (task_id={task_id})")


__all__ = ["CancelNotAllowedError", "cancel_task"]
