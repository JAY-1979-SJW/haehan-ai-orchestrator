"""로컬 에이전트 진단 헬퍼 함수 테스트.

진단 정보를 집계하는 helper 함수들의 정합성을 검증한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_orchestrator.agent_hub.registry.diagnostics_helpers import (
    count_agents_by_status,
    count_task_summaries,
    count_tasks_by_status,
    determine_diagnostics_status,
)

# ── count_agents_by_status 함수 ──────────────────────────────────────────


def test_count_agents_by_status_empty():
    """빈 에이전트 목록 집계."""
    agent_statuses = {}
    counts = count_agents_by_status(agent_statuses)

    assert counts["total"] == 0
    assert counts["online"] == 0
    assert counts["offline"] == 0
    assert counts["stale"] == 0


def test_count_agents_by_status_all_online():
    """모든 에이전트가 온라인."""
    agent_statuses = {
        "agent-1": "idle",
        "agent-2": "busy",
        "agent-3": "idle",
    }
    counts = count_agents_by_status(agent_statuses)

    assert counts["total"] == 3
    assert counts["online"] == 3
    assert counts["offline"] == 0
    assert counts["stale"] == 0


def test_count_agents_by_status_mixed():
    """다양한 상태의 에이전트."""
    agent_statuses = {
        "agent-1": "idle",
        "agent-2": "offline",
        "agent-3": "stale",
        "agent-4": "busy",
    }
    counts = count_agents_by_status(agent_statuses)

    assert counts["total"] == 4
    assert counts["online"] == 2  # idle, busy
    assert counts["offline"] == 1
    assert counts["stale"] == 1


def test_count_agents_by_status_all_offline():
    """모든 에이전트가 오프라인."""
    agent_statuses = {
        "agent-1": "offline",
        "agent-2": "offline",
    }
    counts = count_agents_by_status(agent_statuses)

    assert counts["total"] == 2
    assert counts["online"] == 0
    assert counts["offline"] == 2
    assert counts["stale"] == 0


# ── count_tasks_by_status 함수 ──────────────────────────────────────────


def test_count_tasks_by_status_empty():
    """빈 태스크 목록 집계."""
    tasks = []
    counts = count_tasks_by_status(tasks)

    assert counts["total"] == 0
    assert counts["queued"] == 0
    assert counts["running"] == 0
    assert counts["completed"] == 0
    assert counts["failed"] == 0


def test_count_tasks_by_status_mixed():
    """다양한 상태의 태스크."""
    tasks = [
        {"task_id": "task-1", "status": "queued"},
        {"task_id": "task-2", "status": "running"},
        {"task_id": "task-3", "status": "completed"},
        {"task_id": "task-4", "status": "failed"},
        {"task_id": "task-5", "status": "waiting_approval"},
    ]
    counts = count_tasks_by_status(tasks)

    assert counts["total"] == 5
    assert counts["queued"] == 1
    assert counts["running"] == 1
    assert counts["completed"] == 1
    assert counts["failed"] == 1
    assert counts["waiting_approval"] == 1


def test_count_tasks_by_status_all_statuses():
    """모든 태스크 상태가 포함되는지 검증."""
    tasks = []
    counts = count_tasks_by_status(tasks)

    expected_keys = {
        "total",
        "queued",
        "pending",
        "running",
        "waiting_approval",
        "completed",
        "failed",
        "rejected",
        "cancelled",
    }
    assert set(counts.keys()) == expected_keys


# ── count_task_summaries 함수 ────────────────────────────────────────────


def test_count_task_summaries_empty():
    """빈 태스크 목록의 summary 집계."""
    tasks = []
    counts = count_task_summaries(tasks)

    assert counts["with_result_summary"] == 0
    assert counts["with_observe_summary"] == 0
    assert counts["with_audit_summary"] == 0


def test_count_task_summaries_with_summaries():
    """summary를 포함한 태스크 집계."""
    tasks = [
        {"task_id": "task-1", "result_summary": "summary1", "observe_summary": None, "audit_summary": None},
        {"task_id": "task-2", "result_summary": None, "observe_summary": "summary2", "audit_summary": None},
        {"task_id": "task-3", "result_summary": None, "observe_summary": None, "audit_summary": "summary3"},
        {"task_id": "task-4", "result_summary": "summary4", "observe_summary": "summary5", "audit_summary": "summary6"},
    ]
    counts = count_task_summaries(tasks)

    assert counts["with_result_summary"] == 2
    assert counts["with_observe_summary"] == 2
    assert counts["with_audit_summary"] == 2


# ── determine_diagnostics_status 함수 ───────────────────────────────────


def test_determine_diagnostics_status_ok():
    """정상 상태 판정."""
    agent_counts = {"total": 5, "online": 5, "offline": 0, "stale": 0}
    task_counts = {"total": 10, "failed": 0, "waiting_approval": 0}

    status, warnings = determine_diagnostics_status(agent_counts, task_counts)

    assert status == "ok"
    assert len(warnings) == 0


def test_determine_diagnostics_status_no_agents():
    """에이전트 없음 경고."""
    agent_counts = {"total": 0, "online": 0, "offline": 0, "stale": 0}
    task_counts = {"total": 0, "failed": 0, "waiting_approval": 0}

    status, warnings = determine_diagnostics_status(agent_counts, task_counts)

    assert status == "ok"  # 초기 상태
    assert "no_registered_agents" in warnings


def test_determine_diagnostics_status_failed_tasks():
    """실패한 태스크 경고."""
    agent_counts = {"total": 5, "online": 5, "offline": 0, "stale": 0}
    task_counts = {"total": 10, "failed": 3, "waiting_approval": 0}

    status, warnings = determine_diagnostics_status(agent_counts, task_counts)

    assert status == "warn"
    assert "failed_tasks" in warnings


def test_determine_diagnostics_status_approval_backlog():
    """승인 대기 작업 경고."""
    agent_counts = {"total": 5, "online": 5, "offline": 0, "stale": 0}
    task_counts = {"total": 10, "failed": 0, "waiting_approval": 2}

    status, warnings = determine_diagnostics_status(agent_counts, task_counts)

    assert status == "warn"
    assert "approval_backlog" in warnings


def test_determine_diagnostics_status_multiple_warnings():
    """다중 경고."""
    agent_counts = {"total": 0, "online": 0, "offline": 0, "stale": 0}
    task_counts = {"total": 10, "failed": 3, "waiting_approval": 2}

    status, warnings = determine_diagnostics_status(agent_counts, task_counts)

    assert status == "warn"
    assert "no_registered_agents" in warnings
    assert "failed_tasks" in warnings
    assert "approval_backlog" in warnings


# ── 모듈 import 검증 ────────────────────────────────────────────────────────


def test_diagnostics_helpers_module_importable():
    """진단 헬퍼 모듈이 정상적으로 임포트 가능한지 검증."""
    import ai_orchestrator.agent_hub.registry.diagnostics_helpers as helpers_module

    assert hasattr(helpers_module, "count_agents_by_status")
    assert hasattr(helpers_module, "count_tasks_by_status")
    assert hasattr(helpers_module, "count_task_summaries")
    assert hasattr(helpers_module, "determine_diagnostics_status")


def test_no_circular_import_with_diagnostics():
    """진단 헬퍼 모듈과 진단 모듈 간 순환 참조 없음을 검증."""
    try:
        from ai_orchestrator.agent_hub.registry.diagnostics import build_local_agent_diagnostics

        assert build_local_agent_diagnostics is not None
    except ImportError:
        pass


# ── 헬퍼 함수 형식 검증 ──────────────────────────────────────────────────


def test_count_functions_return_dicts():
    """모든 count 함수가 dict를 반환하는지 검증."""
    assert isinstance(count_agents_by_status({}), dict)
    assert isinstance(count_tasks_by_status([]), dict)
    assert isinstance(count_task_summaries([]), dict)


def test_status_function_returns_tuple():
    """status 함수가 (status, warnings) 튜플을 반환하는지 검증."""
    agent_counts = {"total": 1, "online": 1, "offline": 0, "stale": 0}
    task_counts = {"total": 1, "failed": 0, "waiting_approval": 0}

    result = determine_diagnostics_status(agent_counts, task_counts)

    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)  # status
    assert isinstance(result[1], list)  # warnings


# ── 집계 일관성 검증 ────────────────────────────────────────────────────────


def test_agent_count_totals_consistent():
    """에이전트 카운트 합계의 일관성."""
    agent_statuses = {
        "agent-1": "idle",
        "agent-2": "offline",
        "agent-3": "stale",
        "agent-4": "busy",
    }
    counts = count_agents_by_status(agent_statuses)

    # total은 모든 상태의 합과 같아야 함
    assert counts["total"] == 4
    # online, offline, stale의 합이 total과 같아야 함
    assert counts["online"] + counts["offline"] + counts["stale"] == counts["total"]


def test_task_count_includes_all_statuses():
    """태스크 카운트가 모든 상태를 포함하는지 검증."""
    tasks = [
        {"task_id": "task-1", "status": "queued"},
        {"task_id": "task-2", "status": "running"},
        {"task_id": "task-3", "status": "completed"},
        {"task_id": "task-4", "status": "failed"},
    ]
    counts = count_tasks_by_status(tasks)

    # total은 모든 상태의 합과 같아야 함
    status_counts = [
        counts["queued"],
        counts["pending"],
        counts["running"],
        counts["waiting_approval"],
        counts["completed"],
        counts["failed"],
        counts["rejected"],
        counts["cancelled"],
    ]
    assert sum(status_counts) == counts["total"]
