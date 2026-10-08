"""Browser Tool Router.

Routes browser tasks to appropriate backend implementations based on action type and policy.
"""

from __future__ import annotations

from typing import Any

from . import backend_policy, mock_backend
from .schemas import BrowserResult, BrowserTask


def route_browser_task(task: BrowserTask) -> BrowserResult:
    """Route a browser task to the appropriate backend.

    Args:
        task: Browser task request

    Returns:
        Result from the backend handler
    """
    action = task.action
    params = task.params or {}

    # Check policy for this action
    action_policy = backend_policy.get_action_policy(action)

    # Unknown action
    if action_policy is None:
        return BrowserResult(
            success=False,
            action=action,
            data={},
            error=f"unknown browser action: {action}",
            error_code="UNKNOWN_BROWSER_ACTION",
            backend="mock",
        )

    # Action is blocked
    if backend_policy.is_action_blocked(action):
        reason = backend_policy.get_block_reason(action)
        return BrowserResult(
            success=False,
            action=action,
            data={
                "action": action,
                "blocked": True,
                "reason": reason,
            },
            error=f"browser action blocked: {reason}",
            error_code="BROWSER_ACTION_BLOCKED",
            backend="mock",
        )

    # Dispatch to backend based on BrowserTask.backend field
    selected_backend = task.backend or "mock"  # Default to mock if not specified

    if selected_backend == "worker":
        # Route to Browser Worker backend (HTTP)
        from .worker_backend import BrowserWorkerBackend  # lazy import

        worker_backend = BrowserWorkerBackend()
        url = params.get("url", "about:blank")
        task_id = params.get("task_id", f"task-{id(task)}")
        dry_run = params.get("dry_run", True)
        try:
            return worker_backend.execute(task, url, task_id, dry_run)
        except Exception as e:  # noqa: BLE001 - 브라우저 워커 백엔드 실행 오류를 BrowserResult(success=False, error=...)로 감싸 반환 — fail-closed, 실패를 성공으로 오인하지 않음
            # Handle any unexpected errors
            return BrowserResult(
                success=False,
                action=action,
                data={},
                error=f"worker backend error: {e!s}",
                error_code="BROWSER_WORKER_ERROR",
                backend="worker",
            )
    else:
        # Default to mock backend
        return mock_backend.handle_task(task)


def route_browser_task_with_params(action: str, params: dict[str, Any] | None = None) -> BrowserResult:
    """Convenience function to route with action string and params dict.

    Args:
        action: Browser action name
        params: Action parameters

    Returns:
        Result from backend handler
    """
    # Valid actions
    valid_actions = {"inspect", "plan_click", "plan_type", "plan_submit", "execute_click", "execute_type"}

    if action not in valid_actions:
        return BrowserResult(
            success=False,
            action=action,  # type: ignore
            data={},
            error=f"unknown browser action: {action}",
            error_code="UNKNOWN_BROWSER_ACTION",
            backend="mock",
        )

    task = BrowserTask(action=action, params=params or {})  # type: ignore
    return route_browser_task(task)
