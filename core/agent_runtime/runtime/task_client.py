"""
로컬 에이전트 task client

서버에서 pending task를 가져와 Playwright로 실행하는 polling client.
LOCAL_PLAYWRIGHT task만 실행 대상으로 인정한다.
USER_DIRECT_REQUIRED / BLOCKED는 실행하지 않고 상태만 보고한다.

금지:
- 서버 인증정보 하드코딩
- secret 출력
- cookie/session 전송
- 민감 필드 포함 결과 전송
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.local_task_protocol import (
    EXEC_MODE_LOCAL_PLAYWRIGHT,
    STATUS_BLOCKED,
    STATUS_FAILED,
    build_result,
    validate_task,
)
from ai_orchestrator.server.local_agent_task_api import (
    get_pending_local_agent_task,
    mark_task_assigned,
    receive_local_agent_result,
)
from core.agent_runtime.runtime.result_sanitizer import sanitize_result
from core.agent_runtime.runtime.security_guard import (
    validate_task_before_run,
)

# ── polling 설정 ───────────────────────────────────────────────────────────────

DEFAULT_POLL_INTERVAL_SEC = 5
DEFAULT_MAX_POLLS = 0  # 0 = 무한


def poll_and_run_once(runner_fn: Any) -> dict[str, Any] | None:
    """
    pending task를 하나 가져와 실행하고 결과를 반환한다.
    실행할 task가 없으면 None을 반환한다.

    runner_fn: playwright_runner.run_task와 같은 callable.
               signature: runner_fn(task) -> raw_result dict
    """
    tasks = get_pending_local_agent_task(limit=1)
    if not tasks:
        return None

    record = tasks[0]
    task = record.get("payload", {})
    task_id = task.get("task_id", record.get("task_id", ""))

    # task schema 검증
    violations = validate_task(task)
    if violations:
        result = build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=f"task schema 위반: {'; '.join(violations)}",
        )
        receive_local_agent_result(task_id, result)
        return result

    # LOCAL_PLAYWRIGHT 전용
    if task.get("execution_mode") != EXEC_MODE_LOCAL_PLAYWRIGHT:
        result = build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=f"지원하지 않는 execution_mode: {task.get('execution_mode')!r}",
        )
        receive_local_agent_result(task_id, result)
        return result

    # 보안 guard
    guard = validate_task_before_run(task)
    if not guard["allowed"]:
        result = build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_BLOCKED,
            message_ko=guard["reason"],
        )
        receive_local_agent_result(task_id, result)
        return result

    if guard.get("user_direct_required"):
        from ai_orchestrator.contracts.local_task_protocol import STATUS_USER_ACTION_REQUIRED

        result = build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_USER_ACTION_REQUIRED,
            message_ko=guard["reason"],
        )
        receive_local_agent_result(task_id, result)
        return result

    # ASSIGNED 마킹
    mark_task_assigned(task_id)

    # 실행
    try:
        raw_result = runner_fn(task)
    except Exception as exc:  # noqa: BLE001 - 로컬 에이전트 task 실행(runner_fn) 중 예외를 STATUS_FAILED 결과로 변환 — 이미 validate_task_before_run 보안 가드를 통과한 이후 실행 단계의 오류 처리, 실패를 성공으로 위장하지 않음
        result = build_result(
            task_id=task_id,
            ok=False,
            status=STATUS_FAILED,
            message_ko=f"실행 오류: {type(exc).__name__}",
        )
        receive_local_agent_result(task_id, result)
        return result

    # 결과 sanitize
    safe_result = sanitize_result(raw_result)

    # 서버 보고
    receive_local_agent_result(task_id, safe_result)
    return safe_result


