"""로컬 에이전트 진단 헬퍼 함수.

진단 정보 수집 및 집계 함수들을 중앙화한다.
"""

from __future__ import annotations

# ── Agent 상태 집계 ──────────────────────────────────────────────────────────


def count_agents_by_status(agent_statuses: dict[str, str]) -> dict[str, int]:
    """에이전트 상태별 카운트 집계.

    Args:
        agent_statuses: {agent_id: status} 매핑 (idle, busy, offline, stale)

    Returns:
        {
            "total": int,
            "online": int (idle + busy),
            "offline": int,
            "stale": int
        }
    """
    counts = {
        "total": len(agent_statuses),
        "online": sum(1 for s in agent_statuses.values() if s in ("idle", "busy")),
        "offline": sum(1 for s in agent_statuses.values() if s == "offline"),
        "stale": sum(1 for s in agent_statuses.values() if s == "stale"),
    }
    return counts


# ── Task 상태 집계 ──────────────────────────────────────────────────────────


def count_tasks_by_status(tasks: list[dict]) -> dict[str, int]:
    """태스크 상태별 카운트 집계.

    Args:
        tasks: 태스크 dict 목록

    Returns:
        {
            "total": int,
            "queued": int,
            "pending": int,
            "running": int,
            "waiting_approval": int,
            "completed": int,
            "failed": int,
            "rejected": int,
            "cancelled": int
        }
    """
    counts = {
        "total": len(tasks),
        "queued": 0,
        "pending": 0,
        "running": 0,
        "waiting_approval": 0,
        "completed": 0,
        "failed": 0,
        "rejected": 0,
        "cancelled": 0,
    }

    for task in tasks:
        status = task.get("status")
        if status in counts:
            counts[status] += 1
        elif status == "pending":
            counts["pending"] += 1

    return counts


# ── Task Summary 집계 ────────────────────────────────────────────────────────


def count_task_summaries(tasks: list[dict]) -> dict[str, int]:
    """태스크 summary 포함 여부 집계.

    Args:
        tasks: 태스크 dict 목록

    Returns:
        {
            "with_result_summary": int,
            "with_observe_summary": int,
            "with_audit_summary": int
        }
    """
    counts = {
        "with_result_summary": 0,
        "with_observe_summary": 0,
        "with_audit_summary": 0,
    }

    for task in tasks:
        if task.get("result_summary"):
            counts["with_result_summary"] += 1
        if task.get("observe_summary"):
            counts["with_observe_summary"] += 1
        if task.get("audit_summary"):
            counts["with_audit_summary"] += 1

    return counts


# ── 진단 상태 판정 ──────────────────────────────────────────────────────────


def determine_diagnostics_status(agent_counts: dict[str, int], task_counts: dict[str, int]) -> tuple[str, list[str]]:
    """진단 상태와 경고 메시지 판정.

    Args:
        agent_counts: count_agents_by_status() 반환값
        task_counts: count_tasks_by_status() 반환값

    Returns:
        (status: "ok" | "warn" | "error", warnings: [str])
    """
    status = "ok"
    warnings = []

    if agent_counts.get("total", 0) == 0:
        warnings.append("no_registered_agents")

    if task_counts.get("failed", 0) > 0:
        status = "warn"
        warnings.append("failed_tasks")

    if task_counts.get("waiting_approval", 0) > 0:
        status = "warn"
        warnings.append("approval_backlog")

    return status, warnings
