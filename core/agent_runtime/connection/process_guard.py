"""Local Agent 프로세스 감지 및 stale cleanup guard.

실제 프로세스 kill은 dry_run=False 명시 + 사용자 승인 필요.
기본 동작은 dry_run=True (목록 보고만).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core.agent_runtime.connection.status_store import (
    _LOCK_FILE,
    _STATUS_FILE,
    lock_exists,
    lock_task_id,
    read_status,
    release_lock,
    write_status,
)

# idle timeout 기본값 (초)
DEFAULT_IDLE_TIMEOUT_S = 1800


def is_stale(idle_timeout_s: int = DEFAULT_IDLE_TIMEOUT_S) -> bool:
    """stale 여부 판정.

    - lock 파일 존재하나 status가 running=False인 경우
    - status 갱신 후 idle_timeout_s 초과
    """
    if not lock_exists():
        return False
    status = read_status()
    if not status.get("running"):
        return True
    updated_at_str = status.get("updated_at", "")
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
            elapsed = (datetime.now(UTC) - updated_at).total_seconds()
            eff_timeout = status.get("idle_timeout_s", idle_timeout_s)
            if elapsed > eff_timeout:
                return True
        except Exception:  # noqa: BLE001 - 유휴(idle) 상태 판정 보조 함수 - 상태 조회 실패 시 False 반환(유휴 아님으로 간주), 판정 실패가 프로세스 강제종료 등으로 이어지지 않는 안전한 기본값
            pass
    return False


def get_stale_info() -> dict[str, Any]:
    """stale 정보 반환."""
    return {
        "lock_exists": lock_exists(),
        "lock_task_id": lock_task_id(),
        "stale": is_stale(),
        "status": read_status(),
    }


def cleanup_stale_processes(dry_run: bool = True) -> dict[str, Any]:
    """stale 프로세스/lock 정리.

    dry_run=True (기본): 목록만 보고, 실제 정리 없음.
    dry_run=False: 사용자 승인 후에만 호출 — lock 해제 + status 초기화.
    """
    info = get_stale_info()
    candidates = []

    if info["lock_exists"] and info["stale"]:
        candidates.append(
            {
                "type": "stale_lock",
                "path": str(_LOCK_FILE),
                "task_id": info["lock_task_id"],
            }
        )
    if _STATUS_FILE.exists() and not info["status"].get("running"):
        candidates.append(
            {
                "type": "stale_status_file",
                "path": str(_STATUS_FILE),
            }
        )

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "candidates": candidates,
        "cleaned": [],
    }

    if dry_run:
        result["note"] = "dry_run=True: 실제 정리 없음. 목록 확인 후 사용자 승인 필요."
        return result

    # dry_run=False: 실제 정리 (사용자 승인 후 호출)
    for cand in candidates:
        if cand["type"] == "stale_lock":
            release_lock()
            result["cleaned"].append(cand["path"])
        elif cand["type"] == "stale_status_file":
            write_status(running=False, reason="cleanup")
            result["cleaned"].append(cand["path"])

    result["note"] = f"정리 완료: {len(result['cleaned'])}개"
    return result
