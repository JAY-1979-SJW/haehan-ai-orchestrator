"""
서버 로컬 에이전트 task API / adapter

서버 역할: task 생성, safe payload 제공, 결과 수신, 민감값 차단.
서버 금지: 외부 사이트 브라우저 접속, Playwright 실행, 인증정보 저장.

DB schema 변경 없음. in-memory adapter 수준.
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.local_task_protocol import (
    ALLOWED_TASK_ACTIONS,
    build_task,
    validate_result,
)
from ai_orchestrator.server.task_queue_schema import (
    create_task_record,
    get_pending_tasks,
    get_task,
    mark_assigned,
    mark_completed,
    mark_failed,
    validate_no_sensitive_fields,
)

_SERVER_ALLOWED_ACTIONS = frozenset(ALLOWED_TASK_ACTIONS)


def create_local_browser_task(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수, 인자 묶음 변경 시 API 영향)
    action: str,
    target_url: str,
    domain: str = "",
    readonly: bool = True,
    requires_user_presence: bool = False,
    timeout_seconds: int = 300,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    로컬 에이전트 실행용 browser task를 생성한다.

    서버가 외부 사이트를 직접 열지 않는다.
    task payload는 민감 데이터 없음이 보장된다.
    """
    task = build_task(
        action=action,
        target_url=target_url,
        domain=domain,
        readonly=readonly,
        requires_user_presence=requires_user_presence,
        timeout_seconds=timeout_seconds,
        metadata=metadata,
    )
    record = create_task_record(task)
    return record


def get_pending_local_agent_task(limit: int = 10) -> list[dict[str, Any]]:
    """
    로컬 에이전트가 가져갈 PENDING task 목록을 반환한다.
    각 task payload는 sanitize 보장됨.
    """
    tasks = get_pending_tasks(limit=limit)
    return [_safe_task_view(t) for t in tasks]


def mark_task_assigned(task_id: str) -> bool:
    """task를 ASSIGNED 상태로 변경한다."""
    return mark_assigned(task_id)


def receive_local_agent_result(
    task_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    로컬 에이전트 결과를 수신하고 검증 후 저장한다.

    민감 필드가 포함된 결과는 저장하지 않고 BLOCKED 처리한다.
    """
    # 민감값 차단 검증
    sensitive_violations = validate_no_sensitive_fields(result)
    if sensitive_violations:
        mark_failed(task_id, reason=f"민감 필드 포함: {sensitive_violations}")
        return {
            "task_id": task_id,
            "accepted": False,
            "block_reason": sensitive_violations,
        }

    # result schema 검증
    schema_violations = validate_result(result)
    if schema_violations:
        mark_failed(task_id, reason=f"결과 schema 위반: {schema_violations}")
        return {
            "task_id": task_id,
            "accepted": False,
            "block_reason": schema_violations,
        }

    mark_completed(task_id, result)
    return {
        "task_id": task_id,
        "accepted": True,
        "block_reason": None,
    }


def sanitize_task_for_local_agent(task: dict[str, Any]) -> dict[str, Any]:
    """
    task payload에서 민감 필드를 제거하고 안전한 payload를 반환한다.
    """
    violations = validate_no_sensitive_fields(task)
    if violations:
        raise ValueError(f"task에 민감 필드 포함됨: {violations}")
    return dict(task)


def get_task_status(task_id: str) -> dict[str, Any] | None:
    """task 상태를 반환한다."""
    record = get_task(task_id)
    if not record:
        return None
    return {
        "task_id": task_id,
        "state": record["state"],
        "created_at": record["created_at"],
        "assigned_at": record["assigned_at"],
        "completed_at": record["completed_at"],
    }


def _safe_task_view(record: dict[str, Any]) -> dict[str, Any]:
    """task record에서 로컬 에이전트에 전달할 safe view를 생성한다."""
    payload = record.get("payload", {})
    return {
        "task_id": record["task_id"],
        "state": record["state"],
        "created_at": record["created_at"],
        "payload": dict(payload),
    }
