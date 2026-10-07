"""Local Agent 운영 진단용 read-only helper.

diagnostics endpoint에서만 사용.
민감정보 노출 금지 (token_id, params, raw audit/html/url/secret).
allowlist field만 반환.
"""

from __future__ import annotations

from datetime import UTC, datetime

from . import facade as _reg


def _aggregate_tasks(tasks_snapshot: list) -> tuple[dict, dict, tuple]:
    """task 스냅샷 → (task_counts, summary_counts, latest 정보) 집계."""
    task_counts = {
        "total": len(tasks_snapshot),
        "queued": 0,
        "pending": 0,
        "running": 0,
        "waiting_approval": 0,
        "completed": 0,
        "failed": 0,
        "rejected": 0,
        "cancelled": 0,
    }

    summary_counts = {
        "with_result_summary": 0,
        "with_observe_summary": 0,
        "with_audit_summary": 0,
    }

    latest_task_created_at = None
    latest_task_updated_at = None
    latest_task_status = None
    has_observe_summary = False
    has_audit_summary = False

    for task in tasks_snapshot:
        # Task 상태 count
        if task.status in task_counts:
            task_counts[task.status] += 1
        elif task.status == "pending":  # 호환성 (queued/pending 구분)
            task_counts["pending"] += 1

        # Summary count
        if task.result_summary:
            summary_counts["with_result_summary"] += 1
        if task.observe_summary:
            summary_counts["with_observe_summary"] += 1
        if task.audit_summary:
            summary_counts["with_audit_summary"] += 1

        # Latest task timestamp
        if latest_task_created_at is None or task.created_at > latest_task_created_at:
            latest_task_created_at = task.created_at
        if latest_task_updated_at is None or task.updated_at > latest_task_updated_at:
            latest_task_updated_at = task.updated_at
            latest_task_status = task.status
            has_observe_summary = bool(task.observe_summary)
            has_audit_summary = bool(task.audit_summary)

    latest = (
        latest_task_created_at,
        latest_task_updated_at,
        latest_task_status,
        has_observe_summary,
        has_audit_summary,
    )
    return task_counts, summary_counts, latest


def build_local_agent_diagnostics() -> dict:
    """현재 agent/task 상태를 운영 진단용 집계 데이터로 변환.

    반환:
      {
        "status": "ok" | "warn" | "error",
        "schema_version": 1,
        "diagnostics_generated_at": ISO datetime,
        "repo_boundary_status": "not_checked",
        "agents": {
          "total": int,
          "online": int,
          "offline": int,
          "stale": int
        },
        "tasks": {
          "total": int,
          "queued": int,
          "pending": int,
          "running": int,
          "waiting_approval": int,
          "completed": int,
          "failed": int,
          "rejected": int,
          "cancelled": int
        },
        "summaries": {
          "with_result_summary": int,
          "with_observe_summary": int,
          "with_audit_summary": int
        },
        "latest": {
          "task_created_at": ISO datetime | null,
          "task_updated_at": ISO datetime | null,
          "task_status": str | null,
          "has_observe_summary": bool,
          "has_audit_summary": bool
        },
        "warnings": [str]
      }

    보안:
    - token_id 절대 반환 금지
    - params/raw_params 절대 반환 금지
    - raw audit_summary/observe_summary 원본 반환 금지
    - raw events/html/url/query/fragment/headers/body/path 반환 금지
    - secret/token/password/cookie/session 반환 금지
    """
    try:
        # 2026-09-29 수정(defect_index 신규 항목, 치명적 데드락과 함께 발견): 예전엔 호출부
        # (local_agent_router_query.py)가 _reg._lock 을 잡은 채로 이 함수를 불렀는데, 그
        # 락을 없앤 뒤에도 여기서 _agents/_tasks 를 락 없이 그대로 순회하면 다른 스레드의
        # register_agent()/cleanup_agent_and_tasks() 가 동시에 항목을 추가·삭제할 때
        # "dictionary changed size during iteration" RuntimeError 위험이 있다. 락을 아주
        # 짧게만 잡아 스냅샷(list)을 뜨고, 무거운 집계는 락 밖에서 스냅샷을 순회한다 —
        # get_agent_status()/get_active_task_count() 는 각자 필요할 때 _lock 을 다시 짧게
        # 잡으므로(이 시점엔 바깥 락이 이미 풀려 있어) 재진입 데드락도 없다.
        with _reg._lock:
            agents_snapshot = list(_reg._agents.items())
            tasks_snapshot = list(_reg._tasks.values())

        # 1. Agent 상태 집계
        agent_statuses = {}
        for agent_id, agent in agents_snapshot:  # noqa: B007
            status = _reg.get_agent_status(agent_id)
            agent_statuses[agent_id] = status

        agent_counts = {
            "total": len(agents_snapshot),
            "online": sum(1 for s in agent_statuses.values() if s == "idle" or s == "busy"),
            "offline": sum(1 for s in agent_statuses.values() if s == "offline"),
            "stale": sum(1 for s in agent_statuses.values() if s == "stale"),
        }

        # 2. Task 상태 집계
        task_counts, summary_counts, latest = _aggregate_tasks(tasks_snapshot)
        (
            latest_task_created_at,
            latest_task_updated_at,
            latest_task_status,
            has_observe_summary,
            has_audit_summary,
        ) = latest

        # 3. Status 판정
        status = "ok"
        warnings = []

        if agent_counts["total"] == 0:
            warnings.append("no_registered_agents")

        if task_counts["failed"] > 0:
            status = "warn"
            warnings.append("failed_tasks")

        if task_counts["waiting_approval"] > 0:
            status = "warn"
            warnings.append("approval_backlog")

        # 4. 최종 응답 구성
        now_iso = datetime.now(UTC).isoformat()

        return {
            "status": status,
            "schema_version": 1,
            "diagnostics_generated_at": now_iso,
            "repo_boundary_status": "not_checked",  # 초기: 서버 시작 시 별도 점검 필요
            "agents": agent_counts,
            "tasks": task_counts,
            "summaries": summary_counts,
            "latest": {
                "task_created_at": latest_task_created_at,
                "task_updated_at": latest_task_updated_at,
                "task_status": latest_task_status,
                "has_observe_summary": has_observe_summary,
                "has_audit_summary": has_audit_summary,
            },
            "warnings": warnings,
        }

    except Exception:  # noqa: BLE001 - 진단 정보 생성 실패 시 status=error 반환 — 코드 주석대로 원본 예외 텍스트는 노출하지 않음, 읽기 전용 진단
        # 예외 발생 시 상태는 error이지만 raw exception text 반환 금지
        return {
            "status": "error",
            "schema_version": 1,
            "diagnostics_generated_at": datetime.now(UTC).isoformat(),
            "repo_boundary_status": "not_checked",
            "agents": {"total": 0, "online": 0, "offline": 0, "stale": 0},
            "tasks": {
                "total": 0,
                "queued": 0,
                "pending": 0,
                "running": 0,
                "waiting_approval": 0,
                "completed": 0,
                "failed": 0,
                "rejected": 0,
                "cancelled": 0,
            },
            "summaries": {
                "with_result_summary": 0,
                "with_observe_summary": 0,
                "with_audit_summary": 0,
            },
            "latest": {
                "task_created_at": None,
                "task_updated_at": None,
                "task_status": None,
                "has_observe_summary": False,
                "has_audit_summary": False,
            },
            "warnings": ["internal_error"],
        }
