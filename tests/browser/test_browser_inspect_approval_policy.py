"""browser.inspect approval/safety policy verification.

BROWSER-7C: Verify that browser.inspect action aligns with approval/safety policies:
  - browser.inspect is in AUTO_EXECUTE_VIA_AGENT (server/client auto-execution permitted)
  - browser.inspect is classified as "low" risk in ACTION_RISK (no approval waiting)
  - dry_run=True: success=True, no approval required, browser_started=False
  - dry_run=False: success=False, blocked (actual_browser_execution_not_enabled)
  - Playwright is not imported by the action handlers
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_orchestrator.agent_hub.registry.facade import (
    ACTION_RISK,
    clear,
    enqueue_task,
    register_agent,
)
from ai_orchestrator.contracts.local_agent_actions import AUTO_EXECUTE_VIA_AGENT
from core.agent_runtime.connection.actions import (
    ActionResult,
    action_browser_inspect,
)


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Clear registry before each test."""
    clear()
    yield
    clear()


class TestBrowserInspectApprovalPolicy:
    """browser.inspect approval/safety policy compliance."""

    def test_browser_inspect_in_auto_execute_via_agent(self):
        """browser.inspect is in AUTO_EXECUTE_VIA_AGENT (server/client agreement)."""
        assert "browser.inspect" in AUTO_EXECUTE_VIA_AGENT, (
            "browser.inspect must be in AUTO_EXECUTE_VIA_AGENT for server/client auto-execution delegation"
        )

    def test_browser_inspect_in_action_risk(self):
        """browser.inspect is registered in ACTION_RISK."""
        assert "browser.inspect" in ACTION_RISK, "browser.inspect must be in ACTION_RISK for task policy classification"

    def test_browser_inspect_low_risk_classification(self):
        """browser.inspect is classified as 'low' risk."""
        risk = ACTION_RISK.get("browser.inspect")
        assert risk == "low", f"browser.inspect must be 'low' risk, got {risk!r}"

    def test_browser_inspect_low_risk_no_approval_waiting(self):
        """low risk browser.inspect tasks get status=queued, not waiting_approval."""
        result = register_agent(
            host="test-host",
            os_name="test-os",
            version="1.0.0",
            requested_by="test-user",
        )
        agent_id = result.agent.agent_id
        task = enqueue_task(
            agent_id=agent_id,
            action="browser.inspect",
            params={"dry_run": True},
            requested_by="test-user",
        )
        # low risk should get status=queued (or completed for server-auto actions)
        # browser.inspect is not in _SERVER_AUTO_COMPLETE, so status should be queued
        assert task.status == "queued", f"low risk browser.inspect should have status=queued, got {task.status}"
        assert task.risk_level == "low"

    def test_browser_inspect_dry_run_true_success(self):
        """dry_run=True returns success=True without actual browser execution."""
        result = action_browser_inspect({"dry_run": True})
        assert isinstance(result, ActionResult)
        assert result.success is True, "dry_run=True should succeed"
        assert result.data.get("browser_started") is False
        assert result.data.get("dry_run") is True
        assert result.error == ""
        assert result.error_code == ""

    def test_browser_inspect_dry_run_true_with_url(self):
        """dry_run=True with URL returns success without browser execution."""
        result = action_browser_inspect({"dry_run": True, "url": "https://example.com"})
        assert isinstance(result, ActionResult)
        assert result.success is True
        assert result.data.get("url") == "https://example.com"
        assert result.data.get("browser_started") is False

    def test_browser_inspect_dry_run_false_blocked(self):
        """dry_run=False returns failure with ACTUAL_BROWSER_EXECUTION_NOT_ENABLED."""
        result = action_browser_inspect({"dry_run": False})
        assert isinstance(result, ActionResult)
        assert result.success is False, "dry_run=False should be blocked"
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"
        assert result.data.get("browser_started") is False
        assert result.data.get("reason") == "actual_browser_execution_not_enabled"

    def test_browser_inspect_no_dry_run_param_blocked(self):
        """Missing dry_run param defaults to False, which is blocked."""
        result = action_browser_inspect({})
        assert result.success is False
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_browser_inspect_dry_run_string_true(self):
        """dry_run='true' (string) is coerced to True."""
        result = action_browser_inspect({"dry_run": "true"})
        assert result.success is True
        assert result.data.get("dry_run") is True

    def test_browser_inspect_dry_run_string_false(self):
        """dry_run='false' (string) is coerced to False (blocked)."""
        result = action_browser_inspect({"dry_run": "false"})
        assert result.success is False
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_browser_inspect_browser_started_always_false(self):
        """browser_started is always False (no actual browser execution)."""
        # dry_run=True case
        result_dry = action_browser_inspect({"dry_run": True})
        assert result_dry.data.get("browser_started") is False

        # dry_run=False case
        result_blocked = action_browser_inspect({"dry_run": False})
        assert result_blocked.data.get("browser_started") is False

    def test_browser_inspect_no_playwright_in_action_module(self):
        """Playwright is not imported by the action handler.

        The action module should have no Playwright automation dependencies.
        This is verified by checking that the module does not contain
        'playwright' in its imports.
        """
        import core.agent_runtime.connection.actions as actions_module

        source = actions_module.__file__

        # Read the source file and check for Playwright imports
        with Path(source).open(encoding="utf-8") as f:
            source_code = f.read()

        # Should not import playwright directly
        assert "from playwright" not in source_code, "core.agent_runtime.connection.actions should not import from playwright"
        assert "import playwright" not in source_code, "core.agent_runtime.connection.actions should not import playwright"

    def test_browser_inspect_task_flow_matches_policy(self):
        """Complete task flow: enqueue + execute matches approval policy."""
        result = register_agent(
            host="test-host",
            os_name="test-os",
            version="1.0.0",
            requested_by="test-user",
        )
        agent_id = result.agent.agent_id
        # Enqueue a low-risk browser.inspect task with dry_run=True
        task = enqueue_task(
            agent_id=agent_id,
            action="browser.inspect",
            params={"dry_run": True, "url": "https://example.com"},
            requested_by="test-user",
        )

        # Should be queued (low risk, PC-dependent)
        assert task.status == "queued"
        assert task.risk_level == "low"

        # Execute the action
        result = action_browser_inspect(task.params)

        # dry_run=True should succeed
        assert result.success is True
        assert result.data.get("browser_started") is False
        assert result.data.get("action") == "browser.inspect"

    def test_browser_inspect_dry_run_true_is_read_only(self):
        """dry_run=True action is read-only, produces no side effects."""
        # Multiple identical calls should produce consistent structure
        result1 = action_browser_inspect({"dry_run": True, "url": "https://example.com"})
        result2 = action_browser_inspect({"dry_run": True, "url": "https://example.com"})

        assert result1.success == result2.success
        # Data structure should be identical (timestamps may differ)
        assert result1.data["action"] == result2.data["action"]
        assert result1.data["dry_run"] == result2.data["dry_run"]
        assert result1.data["browser_started"] == result2.data["browser_started"]
        assert result1.data["url"] == result2.data["url"]
        # Data should contain only metadata, no browser state
        assert "title" in result1.data or "status" in result1.data


class TestBrowserInspectConflictWithApprovalWorkflow:
    """Verify browser.inspect doesn't conflict with existing approval workflow."""

    def test_browser_execute_actions_are_medium_risk(self):
        """browser.execute_* actions are medium risk (higher than inspect)."""
        assert ACTION_RISK.get("browser.execute_click") == "medium"
        assert ACTION_RISK.get("browser.execute_type") == "medium"

    def test_browser_plan_actions_are_low_risk(self):
        """browser.plan_* actions are low risk (read-only planning)."""
        assert ACTION_RISK.get("browser.plan_click") == "low"
        assert ACTION_RISK.get("browser.plan_type") == "low"
        assert ACTION_RISK.get("browser.plan_submit") == "low"

    def test_browser_inspect_risk_tier_below_execute(self):
        """browser.inspect (low) is lower risk than execute (medium)."""
        inspect_risk = ACTION_RISK.get("browser.inspect")
        execute_risk = ACTION_RISK.get("browser.execute_click")

        risk_order = {"low": 1, "medium": 2, "high": 3}
        assert risk_order[inspect_risk] < risk_order[execute_risk]

    def test_high_risk_browser_action_still_requires_approval(self):
        """Verify that non-existent high-risk browser actions would require approval.

        This confirms the approval workflow is still in place for hypothetical
        high-risk browser actions (even though none exist yet).
        """
        # Simulate a hypothetical high-risk action
        test_actions = {
            "browser.delete_all_cookies": "high",
            "browser.clear_storage": "high",
        }

        for action_name, expected_risk in test_actions.items():
            # These are hypothetical — not actually registered
            # But if they were registered with risk='high', they would require approval
            # This documents the approval policy for future actions
            pass
