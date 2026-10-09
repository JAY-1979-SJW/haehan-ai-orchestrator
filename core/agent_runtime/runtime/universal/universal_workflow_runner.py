"""
Universal Workflow Runner

site profile → capability → workflow template → permission gate → safe result.
모든 사이트 자동화를 공통 runner로 처리한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from core.agent_runtime.runtime.permission.approval_audit_log import (
    log_execution_blocked,
    log_execution_completed,
    log_execution_started,
)
from core.agent_runtime.runtime.permission.delegated_permission_gate import (
    GATE_PASS,
    evaluate_gate,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import (
    get_site_profile,
    is_action_blocked_for_site,
    is_action_direct_required,
)
from core.agent_runtime.runtime.universal.universal_safe_result import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PERMISSION_REQUIRED,
    STATUS_USER_DIRECT_REQUIRED,
    STATUS_WARN_PERMISSION,
    build_universal_result,
)
from core.agent_runtime.runtime.universal.workflow_template_engine import get_template


@dataclass
class _WorkflowState:
    executed: list[str] = field(default_factory=list)
    pending_permission: list[str] = field(default_factory=list)
    user_direct_required: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    audit_ids: list[str] = field(default_factory=list)


def _run_auto_step(
    st: _WorkflowState, action: str, domain: str, task_id: str, runner_fn: Callable | None, dry_run: bool
):
    e = log_execution_started(task_id, action, domain, task_id)
    st.audit_ids.append(e["log_id"])
    if runner_fn and not dry_run:
        runner_fn({"task_id": task_id, "action": action, "domain": domain})
    e2 = log_execution_completed(task_id, action, domain, task_id, ok=True)
    st.audit_ids.append(e2["log_id"])
    st.executed.append(action)


def _run_delegated_step(  # noqa: PLR0913 - 내부 헬퍼, 기존 분기 로직을 그대로 옮긴 것
    st: _WorkflowState,
    action: str,
    domain: str,
    task_id: str,
    pmap: dict[str, str],
    runner_fn: Callable | None,
    dry_run: bool,
):
    permission_id = pmap.get(action) or pmap.get("*")
    gate = evaluate_gate(action, domain, permission_id)
    if gate["gate"] != GATE_PASS:
        st.pending_permission.append(action)
        return
    if dry_run:
        st.executed.append(f"{action}(dry-run-skip)")
        return
    e = log_execution_started(permission_id or "", action, domain, task_id)
    st.audit_ids.append(e["log_id"])
    if runner_fn:
        runner_fn({"task_id": task_id, "action": action, "domain": domain, "permission_id": permission_id})
    e2 = log_execution_completed(permission_id or "", action, domain, task_id, ok=True)
    st.audit_ids.append(e2["log_id"])
    st.executed.append(action)


def _block_step(st: _WorkflowState, action: str, domain: str, reason: str, task_id: str):
    e = log_execution_blocked(action, domain, reason, task_id)
    st.audit_ids.append(e["log_id"])
    st.blocked.append(action)


def _process_step(  # noqa: PLR0913 - 내부 헬퍼, 기존 분기 로직을 그대로 옮긴 것
    st: _WorkflowState,
    step: dict[str, Any],
    site_id: str,
    domain: str,
    task_id: str,
    pmap: dict[str, str],
    runner_fn: Callable | None,
    dry_run: bool,
):
    action = step["action"]
    step_id = step["step_id"]  # noqa: F841

    # BLOCKED 체크
    if is_action_blocked_for_site(site_id, action):
        _block_step(st, action, domain, f"BLOCKED on site {site_id}", task_id)
        return

    # USER_DIRECT 체크
    if is_action_direct_required(site_id, action):
        st.user_direct_required.append(action)
        return

    grade = step.get("risk_level", GRADE_AUTO_ALLOWED)

    if grade == GRADE_BLOCKED:
        _block_step(st, action, domain, "BLOCKED risk_level", task_id)
    elif grade == GRADE_USER_DIRECT:
        st.user_direct_required.append(action)
    elif grade == GRADE_AUTO_ALLOWED:
        _run_auto_step(st, action, domain, task_id, runner_fn, dry_run)
    elif grade == GRADE_USER_DELEGATED:
        _run_delegated_step(st, action, domain, task_id, pmap, runner_fn, dry_run)


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

    st = _WorkflowState()
    for step in template["steps"]:
        domain = profile["domains"][0] if profile.get("domains") else site_id
        _process_step(st, step, site_id, domain, _task_id, pmap, runner_fn, dry_run)

    executed = st.executed
    pending_permission = st.pending_permission
    user_direct_required = st.user_direct_required
    blocked = st.blocked
    audit_ids = st.audit_ids

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


def run_single_action(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
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

    from core.agent_runtime.runtime.permission.delegated_action_executor import (
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
