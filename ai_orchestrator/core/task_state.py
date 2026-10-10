"""Task 상태 머신 (pending / approved / rejected / executed).

기존 approval 모듈의 토큰 상태와 별도로, task-level 상태를 최소로 추적한다.
- pending   : medium 리스크로 승인 토큰이 발급된 상태
- approved  : 승인되어 실행 대기 중
- rejected  : 거절됨
- executed  : 승인 후 실제 실행까지 완료

in-memory 가 기본(단일 프로세스 FastAPI 기준), JSONL 에 append-only 이벤트 저장
(storage/task_states.jsonl) 으로 재시작 시 복구.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal

from .config import LOG_DIR

logger = logging.getLogger(__name__)

TaskState = Literal["pending", "approved", "rejected", "executed"]

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"approved", "rejected"},
    "approved": {"executed"},
    "rejected": set(),
    "executed": set(),
}

_STATE_PATH = LOG_DIR / "task_states.jsonl"
_store: dict[str, dict] = {}
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class TaskRecord:
    task_id: str
    state: TaskState
    risk_level: str = ""
    token_id: str = ""
    requested_by: str = ""
    actor_role: str = ""
    action_type: str = ""
    target: str = ""
    # 실제 실행 재호출을 위한 스냅샷 (민감 원문 미포함 가정 — TaskRequest 필드만)
    task_snapshot: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    approved_by: str = ""
    rejected_by: str = ""
    reason: str = ""
    result: str = ""


def _append_event(event_type: str, rec: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _STATE_PATH.open("a", encoding="utf-8") as f:
            ev = {"event_timestamp": _now().isoformat(), "event_type": event_type, **rec}
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("task_states 기록 실패: %s", e)


def _load() -> None:
    """JSONL 재생으로 _store 복구. last-wins per task_id."""
    global _store
    _store = {}
    if not _STATE_PATH.exists():
        return
    try:
        with _STATE_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tid = ev.get("task_id")
                if not tid:
                    continue
                rec = {k: ev.get(k) for k in TaskRecord.__dataclass_fields__}
                rec.setdefault("task_snapshot", {})
                _store[tid] = rec
    except OSError as e:
        logger.error("task_states 로드 실패: %s", e)
        _store = {}


def clear() -> None:
    """테스트 전용. 인메모리 store 초기화."""
    with _lock:
        _store.clear()


def get_record(task_id: str) -> TaskRecord | None:
    with _lock:
        if not _store:
            _load()
        rec = _store.get(task_id)
    if not rec:
        return None
    return TaskRecord(**rec)


def get_state(task_id: str) -> TaskState | None:
    rec = get_record(task_id)
    return rec.state if rec else None


def _can_transition(current: str, target: str) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


def set_pending(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    task_id: str,
    *,
    risk_level: str,
    token_id: str,
    requested_by: str,
    actor_role: str,
    action_type: str,
    target: str,
    task_snapshot: dict,
) -> TaskRecord:
    """medium 승인 대기 상태로 등록. 이미 존재하면 덮어쓰지 않는다."""
    with _lock:
        if not _store:
            _load()
        if task_id in _store:
            # 같은 task_id 재제출은 무시 (idempotent). 경고만.
            logger.warning("task_state: 중복 set_pending 무시 | task=%s", task_id)
            return TaskRecord(**_store[task_id])
        now = _now().isoformat()
        rec = TaskRecord(
            task_id=task_id,
            state="pending",
            risk_level=risk_level,
            token_id=token_id,
            requested_by=requested_by,
            actor_role=actor_role,
            action_type=action_type,
            target=target,
            task_snapshot=task_snapshot,
            created_at=now,
            updated_at=now,
        )
        _store[task_id] = asdict(rec)
        _append_event("TASK_PENDING", _store[task_id])
        return rec


def mark_approved(task_id: str, actor: str, role: str) -> tuple[TaskRecord | None, str]:
    """pending → approved. 성공 시 (rec, 'approved'). 실패 시 (rec or None, reason)."""
    with _lock:
        if not _store:
            _load()
        rec = _store.get(task_id)
        if not rec:
            return None, "not_found"
        if not _can_transition(rec["state"], "approved"):
            return TaskRecord(**rec), f"invalid_transition:{rec['state']}->approved"
        rec["state"] = "approved"
        rec["approved_by"] = actor
        rec["actor_role"] = role
        rec["updated_at"] = _now().isoformat()
        _append_event("TASK_APPROVED", rec)
        return TaskRecord(**rec), "approved"


def mark_rejected(task_id: str, actor: str, role: str, reason: str = "") -> tuple[TaskRecord | None, str]:
    with _lock:
        if not _store:
            _load()
        rec = _store.get(task_id)
        if not rec:
            return None, "not_found"
        if not _can_transition(rec["state"], "rejected"):
            return TaskRecord(**rec), f"invalid_transition:{rec['state']}->rejected"
        rec["state"] = "rejected"
        rec["rejected_by"] = actor
        rec["actor_role"] = role
        rec["reason"] = reason
        rec["updated_at"] = _now().isoformat()
        _append_event("TASK_REJECTED", rec)
        return TaskRecord(**rec), "rejected"


def mark_executed(task_id: str, result: str) -> tuple[TaskRecord | None, str]:
    with _lock:
        if not _store:
            _load()
        rec = _store.get(task_id)
        if not rec:
            return None, "not_found"
        if not _can_transition(rec["state"], "executed"):
            return TaskRecord(**rec), f"invalid_transition:{rec['state']}->executed"
        rec["state"] = "executed"
        rec["result"] = result
        rec["updated_at"] = _now().isoformat()
        _append_event("TASK_EXECUTED", rec)
        return TaskRecord(**rec), "executed"


__all__ = [
    "TaskRecord",
    "TaskState",
    "clear",
    "get_record",
    "get_state",
    "mark_approved",
    "mark_executed",
    "mark_rejected",
    "set_pending",
]
