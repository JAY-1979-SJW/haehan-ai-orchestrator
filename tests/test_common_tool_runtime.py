import pytest

from ai_orchestrator.agent_hub.action_registry import requires_user_approval
from core.agent_runtime.runtime.common_tool_runtime import (
    EXECUTION_LOCAL_AGENT,
    PHASE_BLOCKED,
    PHASE_COMPLETED,
    RISK_READ,
    RISK_WRITE,
    TOOL_BROWSER,
    CommonToolRuntimeError,
    build_common_tool_result,
    build_common_tool_task,
    dry_run_common_tool_flow,
    validate_common_tool_result,
    validate_common_tool_task,
)


def test_readonly_browser_task_validates_and_dry_runs():
    task = build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="browser.open_url.readonly",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_READ,
        params={"target_url_host": "example.com"},
    )

    result = dry_run_common_tool_flow(task)

    assert validate_common_tool_task(task) == []
    assert result["ok"] is True
    assert result["phase"] == PHASE_COMPLETED
    assert result["data"]["dry_run"] is True


def test_write_task_requires_approval_id():
    with pytest.raises(CommonToolRuntimeError):
        build_common_tool_task(
            tool_namespace=TOOL_BROWSER,
            action="browser.submit_with_user_approval",
            execution_location=EXECUTION_LOCAL_AGENT,
            risk_level=RISK_WRITE,
            requires_approval=True,
            approval_id=None,
        )


def test_dry_run_blocks_approval_required_task_without_approval():
    task = {
        "schema_version": "common-tool-runtime/v1",
        "task_id": "approval-missing",
        "tool_namespace": TOOL_BROWSER,
        "action": "browser.submit_with_user_approval",
        "execution_location": EXECUTION_LOCAL_AGENT,
        "risk_level": RISK_WRITE,
        "requires_approval": True,
        "approval_id": None,
        "params": {},
        "phase": "requested",
        "created_at": "2026-05-24T00:00:00+00:00",
        "metadata": {},
    }

    result = dry_run_common_tool_flow(task)

    assert result["ok"] is False
    assert result["phase"] == PHASE_BLOCKED
    assert result["error_code"] == "COMMON_TOOL_CONTRACT_VIOLATION"


def test_write_task_with_approval_dry_runs():
    task = build_common_tool_task(
        tool_namespace=TOOL_BROWSER,
        action="browser.submit_with_user_approval",
        execution_location=EXECUTION_LOCAL_AGENT,
        risk_level=RISK_WRITE,
        requires_approval=True,
        approval_id="approval-ok",
    )

    result = dry_run_common_tool_flow(task)

    assert result["ok"] is True
    assert result["phase"] == PHASE_COMPLETED


def test_sensitive_fields_are_rejected_recursively():
    task = {
        "schema_version": "common-tool-runtime/v1",
        "task_id": "sensitive",
        "tool_namespace": TOOL_BROWSER,
        "action": "browser.open_url.readonly",
        "execution_location": EXECUTION_LOCAL_AGENT,
        "risk_level": RISK_READ,
        "requires_approval": False,
        "approval_id": None,
        "params": {"nested": {"authorization": "Bearer <redacted>"}},
        "phase": "requested",
        "created_at": "2026-05-24T00:00:00+00:00",
        "metadata": {},
    }

    violations = validate_common_tool_task(task)

    assert violations
    assert "authorization" in violations[0]


def test_common_tool_result_keeps_safe_flags_locked():
    result = build_common_tool_result(task_id="result-ok", ok=True, phase=PHASE_COMPLETED)

    assert validate_common_tool_result(result) == []
    result["token_exported"] = True

    assert validate_common_tool_result(result)


def test_implemented_browser_write_action_requires_user_approval():
    assert requires_user_approval("browser.submit_with_user_approval") is True
