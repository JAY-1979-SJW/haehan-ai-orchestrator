"""로컬 에이전트 cleanup 정책 (safe cleanup 판정 및 검증).

smoke-test residual 정리를 위한 안전장치 기반 cleanup API.

정책:
  - smoke-test-* label/host만 cleanup 대상
  - offline 상태만 cleanup 대상
  - pending/running task가 있으면 cleanup 거부
  - completed/cancelled/failed task만 cleanup 가능
  - dry_run=true (기본): preview만 반환, 삭제 안 함
  - dry_run=false: force=true + confirm 정확 일치 필수
  - confirm 형식: CLEANUP_SMOKE_TEST_{agent_id}
  - response/audit 민감값 미포함
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CleanupPolicy:
    """cleanup 판정 결과."""

    eligible: bool
    reason: str  # eligible | non_smoke | not_offline | blocking_tasks | missing_confirm | confirm_mismatch | ...
    task_count: int = 0
    task_status_counts: dict[str, int] | None = None
    candidate_task_ids: list[str] | None = None


def is_smoke_test_agent(host: str, label: str = "", smoke_test: bool = False) -> bool:
    """smoke-test 패턴 확인.

    host 또는 label이 'smoke-test-'로 시작하거나, smoke_test=true이면 smoke-test agent로 판정.
    """
    if smoke_test:
        return True
    host_is_smoke = host and host.lower().startswith("smoke-test-")
    label_is_smoke = label and label.lower().startswith("smoke-test-")
    return bool(host_is_smoke or label_is_smoke)


def is_agent_offline(agent_status: str) -> bool:
    """agent가 offline 상태인지 확인."""
    return agent_status == "offline"


def has_blocking_tasks(task_statuses: list[str]) -> bool:
    """pending/running/queued 상태 task가 있는지 확인."""
    blocking_statuses = {"pending", "running", "queued", "waiting_approval", "delivered", "cancel_requested"}
    return any(status in blocking_statuses for status in task_statuses)


def get_cleanup_eligible_tasks(task_statuses: list[str]) -> list[str]:
    """cleanup 가능한 task status 목록 (completed/cancelled/failed만)."""
    eligible_statuses = {"completed", "cancelled", "failed"}
    return [status for status in task_statuses if status in eligible_statuses]


def build_cleanup_confirm(agent_id: str) -> str:
    """cleanup 확인 문구 생성."""
    return f"CLEANUP_SMOKE_TEST_{agent_id}"


def validate_cleanup_request(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    agent_id: str,
    host: str,
    label: str,
    agent_status: str,
    task_statuses: list[str],
    dry_run: bool,
    force: bool,
    confirm: str | None,
    smoke_test: bool = False,
) -> CleanupPolicy:
    """cleanup 요청 검증.

    Returns:
        CleanupPolicy 객체: eligible 여부, reason, task_count, counts

    Rules:
    1. smoke-test agent만 eligible
    2. offline agent만 eligible
    3. blocking task 있으면 ineligible
    4. dry_run=true: force/confirm 무시, 단순 preview
    5. dry_run=false: force=true + confirm 정확 일치 필수
    """
    # Rule 1: smoke-test 확인
    if not is_smoke_test_agent(host, label, smoke_test):
        return CleanupPolicy(
            eligible=False,
            reason="non_smoke_agent",
            task_count=len(task_statuses),
        )

    # Rule 2: offline 확인
    if not is_agent_offline(agent_status):
        return CleanupPolicy(
            eligible=False,
            reason=f"not_offline_status:{agent_status}",
            task_count=len(task_statuses),
        )

    # Rule 3: blocking task 확인
    if has_blocking_tasks(task_statuses):
        return CleanupPolicy(
            eligible=False,
            reason="blocking_tasks_present",
            task_count=len(task_statuses),
        )

    # Rule 4: dry_run=true이면 이 시점에서 eligible로 판정
    if dry_run:
        task_status_counts = {status: task_statuses.count(status) for status in set(task_statuses)}
        eligible_tasks = get_cleanup_eligible_tasks(task_statuses)
        return CleanupPolicy(
            eligible=True,
            reason="eligible_dry_run",
            task_count=len(task_statuses),
            task_status_counts=task_status_counts,
            candidate_task_ids=eligible_tasks,
        )

    # Rule 5: dry_run=false이면 force와 confirm 검증
    if not force:
        return CleanupPolicy(
            eligible=False,
            reason="force_required_for_actual_cleanup",
            task_count=len(task_statuses),
        )

    expected_confirm = build_cleanup_confirm(agent_id)
    if not confirm:
        return CleanupPolicy(
            eligible=False,
            reason="confirm_required",
            task_count=len(task_statuses),
        )

    if confirm != expected_confirm:
        return CleanupPolicy(
            eligible=False,
            reason="confirm_mismatch",
            task_count=len(task_statuses),
        )

    # All rules passed
    task_status_counts = {status: task_statuses.count(status) for status in set(task_statuses)}
    eligible_tasks = get_cleanup_eligible_tasks(task_statuses)
    return CleanupPolicy(
        eligible=True,
        reason="eligible_for_cleanup",
        task_count=len(task_statuses),
        task_status_counts=task_status_counts,
        candidate_task_ids=eligible_tasks,
    )
