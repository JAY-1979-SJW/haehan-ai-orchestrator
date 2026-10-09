"""Local Agent On-Demand Controller.

AI가 작업 단위로 local agent를 start/stop 한다.
상시 데몬 금지. Windows service 등록 금지. 자동 재시작 금지.
cookie/session/token/password 접근 금지.
data/sessions/*.json 접근 금지.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from core.agent_runtime.connection.process_guard import cleanup_stale_processes
from core.agent_runtime.connection.status_store import (
    acquire_lock,
    lock_exists,
    read_status,
    release_lock,
    write_status,
)

# ── approval gate decision 상수 ───────────────────────────────────────

DECISION_BLOCKED = "BLOCKED"
DECISION_LOCAL_AGENT_REQUIRED = "LOCAL_AGENT_REQUIRED"
DECISION_USER_DIRECT_REQUIRED = "USER_DIRECT_REQUIRED"
DECISION_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
DECISION_READ_ONLY_ALLOWED = "READ_ONLY_ALLOWED"
DECISION_DRAFT_ALLOWED = "DRAFT_ALLOWED"

_STARTABLE_DECISIONS = frozenset(
    {
        DECISION_LOCAL_AGENT_REQUIRED,
        DECISION_APPROVAL_REQUIRED,
    }
)

# ── approval 검증 ─────────────────────────────────────────────────────


def _validate_approval(approval: dict[str, Any]) -> dict[str, Any]:
    """승인 정보를 검증하고 start 가능 여부를 반환한다."""
    decision = approval.get("decision", "")

    if approval.get("blocked") or decision == DECISION_BLOCKED:
        return {"ok": False, "reason": f"BLOCKED: {approval.get('reason', '')}"}

    if decision == DECISION_USER_DIRECT_REQUIRED:
        return {"ok": False, "reason": "USER_DIRECT_REQUIRED: 사용자가 직접 수행해야 합니다."}

    if decision not in _STARTABLE_DECISIONS:
        return {
            "ok": False,
            "reason": f"decision '{decision}'은 local agent start 대상이 아닙니다.",
        }

    expires_at = approval.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if datetime.now(UTC) > exp:
                return {"ok": False, "reason": "승인이 만료되었습니다."}
        except Exception:  # noqa: BLE001 - 승인 만료시각(expires_at) 파싱 실패시 승인거부(ok:False)로 fail-closed 처리 — 상태조회 함수의 경과시간 계산 실패는 elapsed_s 표시 생략일 뿐 running 상태 판정에는 영향 없음
            return {"ok": False, "reason": "expires_at 형식 오류."}

    return {"ok": True}


# ── 공개 API ──────────────────────────────────────────────────────────


def start_local_agent(
    task_id: str | None,
    domain: str,
    approved_scope: list[str],
    approval: dict[str, Any] | None = None,
    idle_timeout_s: int = 1800,
    action: str = "",
) -> dict[str, Any]:
    """승인된 작업 시작 시 호출.

    중복 start 방지. approval gate 검사. lock 획득 후 status 기록.
    실제 브라우저 실행 없음. 외부 사이트 접속 없음.
    """
    if approval:
        check = _validate_approval(approval)
        if not check["ok"]:
            return {"ok": False, "error": check["reason"]}

    if lock_exists():
        status = read_status()
        return {
            "ok": False,
            "error": "이미 실행 중인 작업이 있습니다.",
            "status": status,
        }

    effective_task_id = task_id or str(uuid.uuid4())
    if not acquire_lock(effective_task_id):
        return {"ok": False, "error": "lock 획득 실패 (경합)."}

    write_status(
        running=True,
        task_id=effective_task_id,
        domain=domain,
        action=action,
        approved_scope=approved_scope,
        idle_timeout_s=idle_timeout_s,
    )

    return {
        "ok": True,
        "task_id": effective_task_id,
        "domain": domain,
        "action": action,
        "approved_scope": approved_scope,
        "started_at": datetime.now(UTC).isoformat(),
        "idle_timeout_s": idle_timeout_s,
    }


def get_local_agent_status() -> dict[str, Any]:
    """현재 실행 상태를 반환한다.

    secret/session/cookie/token 값 포함 금지.
    """
    status = read_status()
    if not status.get("running"):
        return {"running": False, "lock_exists": lock_exists()}

    started_at_str = status.get("updated_at", "")
    elapsed_s: float | None = None
    if started_at_str:
        try:
            started = datetime.fromisoformat(started_at_str)
            elapsed_s = (datetime.now(UTC) - started).total_seconds()
        except Exception:  # noqa: BLE001 - 승인 만료시각(expires_at) 파싱 실패시 승인거부(ok:False)로 fail-closed 처리 — 상태조회 함수의 경과시간 계산 실패는 elapsed_s 표시 생략일 뿐 running 상태 판정에는 영향 없음
            pass

    return {
        "running": True,
        "task_id": status.get("task_id", ""),
        "domain": status.get("domain", ""),
        "action": status.get("action", ""),
        "approved_scope": status.get("approved_scope", []),
        "idle_timeout_s": status.get("idle_timeout_s", 1800),
        "elapsed_s": elapsed_s,
        "lock_exists": lock_exists(),
    }


def stop_local_agent(reason: str = "completed") -> dict[str, Any]:
    """작업 완료/실패/취소 시 호출.

    lock 해제. status 업데이트.
    """
    was_running = read_status().get("running", False)
    write_status(running=False, reason=reason)
    release_lock()
    return {
        "ok": True,
        "stopped_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "was_running": was_running,
    }


def cleanup_stale(dry_run: bool = True) -> dict[str, Any]:
    """stale 프로세스/lock 정리 위임.

    기본 dry_run=True. 실제 정리는 사용자 승인 후 dry_run=False.
    """
    return cleanup_stale_processes(dry_run=dry_run)
