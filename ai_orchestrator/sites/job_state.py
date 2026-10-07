"""사이트 자동화 작업의 상태 머신 (pause/resume 지원).

기존 `ai_orchestrator/core/task_state.py` 는 승인 토큰 기반 control-plane 상태(pending/approved/
rejected/executed)를 다룬다. 이 모듈은 **사이트 자동화 실행(job) 레벨**의 일시정지/재개를 위한
별도 상태 저장소다. 두 상태는 직교한다.

상태:
    RUNNING              — 실행 중
    PAUSED_FOR_REAUTH    — 세션 만료로 사람 재인증 대기
    RESUMABLE            — 재인증 성공, 재개 가능
    DONE                 — 정상 완료
    FAILED               — 복구 불가 실패

전이:
    RUNNING → PAUSED_FOR_REAUTH → RESUMABLE → RUNNING → DONE
    RUNNING → FAILED
    PAUSED_FOR_REAUTH → FAILED (재인증 타임아웃/취소)

저장:
    storage/site_jobs.jsonl  — append-only 이벤트. 마지막 레코드 기준으로 복구.
    민감 원문 금지 (쿠키/비밀번호/OTP/Authorization 헤더).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ..core.config import LOG_DIR

logger = logging.getLogger(__name__)

JobStatus = Literal[
    "RUNNING",
    "PAUSED_FOR_REAUTH",
    "RESUMABLE",
    "DONE",
    "FAILED",
]

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "RUNNING": {"PAUSED_FOR_REAUTH", "DONE", "FAILED"},
    "PAUSED_FOR_REAUTH": {"RESUMABLE", "FAILED"},
    "RESUMABLE": {"RUNNING", "FAILED"},
    "DONE": set(),
    "FAILED": set(),
}

_JOBS_PATH = LOG_DIR / "site_jobs.jsonl"
_store: dict[str, dict] = {}
_lock = threading.Lock()
_loaded = False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class JobRecord:
    job_id: str
    site_id: str
    status: JobStatus = "RUNNING"
    current_step: str = ""
    cursor: str = ""
    paused_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    # 민감 원문 금지. 재개 시 필요한 비-민감 파라미터만.
    params: dict = field(default_factory=dict)
    result_summary: str = ""


def _append_event(event_type: str, rec: dict) -> None:
    try:
        _JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _JOBS_PATH.open("a", encoding="utf-8") as f:
            ev = {"event_timestamp": _now_iso(), "event_type": event_type, **rec}
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("site_jobs 기록 실패: %s", e)


def _load() -> None:
    """JSONL 재생으로 _store 복구. 같은 job_id 는 last-wins."""
    global _store, _loaded
    _store = {}
    if _JOBS_PATH.exists():
        try:
            with _JOBS_PATH.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    jid = ev.get("job_id")
                    if not jid:
                        continue
                    rec = {k: ev.get(k) for k in JobRecord.__dataclass_fields__}
                    rec.setdefault("params", {})
                    _store[jid] = rec
        except OSError as e:
            logger.error("site_jobs 로드 실패: %s", e)
    _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        _load()


def clear() -> None:
    """테스트 전용 — 인메모리 스토어 초기화 (파일은 건드리지 않음)."""
    global _loaded
    with _lock:
        _store.clear()
        _loaded = True  # 테스트에서 빈 상태를 유지하기 위해 이미 로드됨으로 표시


def _can_transition(current: str, target: str) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


def start(
    *,
    job_id: str,
    site_id: str,
    current_step: str = "",
    params: dict | None = None,
) -> JobRecord:
    """job 시작 — RUNNING 으로 등록. 중복 job_id 는 무시(idempotent).

    params 는 재개 시 필요한 비-민감 파라미터만 담아야 한다.
    """
    with _lock:
        _ensure_loaded()
        if job_id in _store:
            existing = _store[job_id]
            logger.warning(
                "job_state: 중복 start 무시 | job=%s existing_status=%s",
                job_id,
                existing.get("status"),
            )
            return JobRecord(**existing)
        now = _now_iso()
        rec = JobRecord(
            job_id=job_id,
            site_id=site_id,
            status="RUNNING",
            current_step=current_step,
            params=dict(params or {}),
            created_at=now,
            updated_at=now,
        )
        _store[job_id] = asdict(rec)
        _append_event("JOB_STARTED", _store[job_id])
        return rec


def _transition(  # noqa: PLR0913 - 작업 상태 전이 내부 헬퍼, 필드 나열형
    job_id: str,
    target: JobStatus,
    *,
    event_type: str,
    current_step: str | None = None,
    cursor: str | None = None,
    paused_reason: str | None = None,
    result_summary: str | None = None,
) -> tuple[JobRecord | None, str]:
    with _lock:
        _ensure_loaded()
        rec = _store.get(job_id)
        if not rec:
            return None, "not_found"
        if not _can_transition(rec["status"], target):
            return JobRecord(**rec), f"invalid_transition:{rec['status']}->{target}"
        rec["status"] = target
        if current_step is not None:
            rec["current_step"] = current_step
        if cursor is not None:
            rec["cursor"] = cursor
        if paused_reason is not None:
            rec["paused_reason"] = paused_reason
        if result_summary is not None:
            rec["result_summary"] = result_summary
        rec["updated_at"] = _now_iso()
        _append_event(event_type, rec)
        return JobRecord(**rec), target.lower()


def pause_for_reauth(
    job_id: str,
    *,
    current_step: str,
    cursor: str = "",
    paused_reason: str = "session_expired",
) -> tuple[JobRecord | None, str]:
    """RUNNING → PAUSED_FOR_REAUTH. 세션 만료 감지 시 호출."""
    return _transition(
        job_id,
        "PAUSED_FOR_REAUTH",
        event_type="JOB_PAUSED_FOR_REAUTH",
        current_step=current_step,
        cursor=cursor,
        paused_reason=paused_reason,
    )


def mark_resumable(job_id: str) -> tuple[JobRecord | None, str]:
    """PAUSED_FOR_REAUTH → RESUMABLE. 재인증 성공 시 호출."""
    return _transition(
        job_id,
        "RESUMABLE",
        event_type="JOB_RESUMABLE",
        paused_reason="",
    )


def resume(job_id: str) -> tuple[JobRecord | None, str]:
    """RESUMABLE → RUNNING. 실제 실행 재시작 시 호출."""
    return _transition(job_id, "RUNNING", event_type="JOB_RESUMED")


def mark_done(job_id: str, result_summary: str = "") -> tuple[JobRecord | None, str]:
    return _transition(
        job_id,
        "DONE",
        event_type="JOB_DONE",
        result_summary=result_summary,
    )


def mark_failed(
    job_id: str,
    *,
    reason: str,
) -> tuple[JobRecord | None, str]:
    """어느 상태에서든 FAILED 로 전이."""
    with _lock:
        _ensure_loaded()
        rec = _store.get(job_id)
        if not rec:
            return None, "not_found"
        if rec["status"] in ("DONE", "FAILED"):
            return JobRecord(**rec), f"invalid_transition:{rec['status']}->FAILED"
        rec["status"] = "FAILED"
        rec["paused_reason"] = reason
        rec["updated_at"] = _now_iso()
        _append_event("JOB_FAILED", rec)
        return JobRecord(**rec), "failed"


def get(job_id: str) -> JobRecord | None:
    with _lock:
        _ensure_loaded()
        rec = _store.get(job_id)
    return JobRecord(**rec) if rec else None


def list_by_status(status: JobStatus) -> list[JobRecord]:
    with _lock:
        _ensure_loaded()
        return [JobRecord(**r) for r in _store.values() if r.get("status") == status]


__all__ = [
    "JobRecord",
    "JobStatus",
    "clear",
    "get",
    "list_by_status",
    "mark_done",
    "mark_failed",
    "mark_resumable",
    "pause_for_reauth",
    "resume",
    "start",
]
