"""
Universal Workflow Runner

site profile → capability → workflow template → permission gate → safe result.
모든 사이트 자동화를 공통 runner로 처리한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from ai_orchestrator.local_agent.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from ai_orchestrator.local_agent.approval_audit_log import (
    log_execution_blocked,
    log_execution_completed,
    log_execution_started,
)
from ai_orchestrator.local_agent.delegated_permission_gate import (
    GATE_PASS,
    evaluate_gate,
)
from ai_orchestrator.local_agent.site_profile_registry import (
    get_site_profile,
    is_action_blocked_for_site,
    is_action_direct_required,
)
from ai_orchestrator.local_agent.universal_safe_result import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PERMISSION_REQUIRED,
    STATUS_USER_DIRECT_REQUIRED,
    STATUS_WARN_PERMISSION,
    build_universal_result,
)
from ai_orchestrator.local_agent.workflow_template_engine import get_template


def run_workflow(
    site_id: str,
    workflow_id: str,
    permission_map: dict[str, str] | None = None,
    runner_fn: Callable | None = None,
    task_id: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    site profile + workflow template 기반 통합 실행기.

    permission_map: {action: permission_id} 매핑.
    runner_fn: 실제 Playwright 실행 함수.
    dry_run: True면 AUTO 단계만 dry-run, DELEGATED는 권한 확인만.
    """
    _task_id = task_id or str(uuid.uuid4())
    pmap = permission_map or {}

    profile = get_site_profile(site_id)
    if not profile:
        return build_universal_result(
            task_id=_task_id,
            site_id=site_id,
            workflow_id=workflow_id,
            status=STATUS_FAILED,
            message_ko=f"미등록 site: {site_id!r}",
        )

    template = get_template(workflow_id)
    if not template:
        return build_universal_result(
            task_id=_task_id,
            site_id=site_id,
            workflow_id=workflow_id,
            status=STATUS_FAILED,
            message_ko=f"미등록 workflow: {workflow_id!r}",
        )

    executed: list[str] = []
    pending_permission: list[str] = []
    user_direct_required: list[str] = []
    blocked: list[str] = []
    audit_ids: list[str] = []

    for step in template["steps"]:
        action = step["action"]
        step_id = step["step_id"]  # noqa: F841
        domain = profile["domains"][0] if profile.get("domains") else site_id

        # BLOCKED 체크
        if is_action_blocked_for_site(site_id, action):
            e = log_execution_blocked(action, domain, f"BLOCKED on site {site_id}", _task_id)
            audit_ids.append(e["log_id"])
            blocked.append(action)
            continue

        # USER_DIRECT 체크
        if is_action_direct_required(site_id, action):
            user_direct_required.append(action)
            continue

        grade = step.get("risk_level", GRADE_AUTO_ALLOWED)

        if grade == GRADE_BLOCKED:
            e = log_execution_blocked(action, domain, "BLOCKED risk_level", _task_id)
            audit_ids.append(e["log_id"])
            blocked.append(action)

        elif grade == GRADE_USER_DIRECT:
            user_direct_required.append(action)

        elif grade == GRADE_AUTO_ALLOWED:
            e = log_execution_started(_task_id, action, domain, _task_id)
            audit_ids.append(e["log_id"])
            if runner_fn and not dry_run:
                runner_fn({"task_id": _task_id, "action": action, "domain": domain})
            e2 = log_execution_completed(_task_id, action, domain, _task_id, ok=True)
            audit_ids.append(e2["log_id"])
            executed.append(action)

        elif grade == GRADE_USER_DELEGATED:
            permission_id = pmap.get(action) or pmap.get("*")
            gate = evaluate_gate(action, domain, permission_id)
            if gate["gate"] == GATE_PASS:
                if not dry_run:
                    e = log_execution_started(permission_id or "", action, domain, _task_id)
                    audit_ids.append(e["log_id"])
                    if runner_fn:
                        runner_fn(
                            {"task_id": _task_id, "action": action, "domain": domain, "permission_id": permission_id}
                        )
                    e2 = log_execution_completed(permission_id or "", action, domain, _task_id, ok=True)
                    audit_ids.append(e2["log_id"])
                    executed.append(action)
                else:
                    executed.append(f"{action}(dry-run-skip)")
            else:
                pending_permission.append(action)

    # 최종 상태 판정
    if blocked:
        final_status = STATUS_BLOCKED
    elif user_direct_required:
        final_status = STATUS_USER_DIRECT_REQUIRED
    elif pending_permission:
        final_status = STATUS_WARN_PERMISSION
    else:
        final_status = STATUS_COMPLETED

    return build_universal_result(
        task_id=_task_id,
        site_id=site_id,
        workflow_id=workflow_id,
        status=final_status,
        actions_executed=executed,
        actions_pending_permission=pending_permission,
        actions_user_direct_required=user_direct_required,
        blocked_actions=blocked,
        audit_log_ids=audit_ids,
        message_ko=f"workflow={workflow_id} site={site_id} status={final_status}",
    )


def run_single_action(
    site_id: str,
    action: str,
    domain: str = "",
    permission_id: str | None = None,
    content: str = "",
    runner_fn: Callable | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """
    단일 action을 site profile 기반으로 실행한다.
    workflow template 없이 단건 실행.
    """
    _task_id = task_id or str(uuid.uuid4())
    profile = get_site_profile(site_id)
    _domain = domain or (profile["domains"][0] if profile and profile.get("domains") else site_id)

    from ai_orchestrator.local_agent.delegated_action_executor import (
        EXEC_ALLOWED,
        EXEC_BLOCKED,
        EXEC_NEED_PERMISSION,
        EXEC_USER_DIRECT,
        execute_delegated_action,
    )

    result = execute_delegated_action(
        action=action,
        domain=_domain,
        permission_id=permission_id,
        content=content,
        task_id=_task_id,
    )

    status_map = {
        EXEC_ALLOWED: STATUS_COMPLETED,
        EXEC_BLOCKED: STATUS_BLOCKED,
        EXEC_NEED_PERMISSION: STATUS_PERMISSION_REQUIRED,
        EXEC_USER_DIRECT: STATUS_USER_DIRECT_REQUIRED,
    }
    return build_universal_result(
        task_id=_task_id,
        site_id=site_id,
        status=status_map.get(result["status"], STATUS_FAILED),
        actions_executed=[action] if result.get("ok") else [],
        blocked_actions=[action] if result["status"] == EXEC_BLOCKED else [],
        safe_outputs={"action_result": result.get("result", {})},
        message_ko=result.get("result", {}).get("message_ko", ""),
    )
