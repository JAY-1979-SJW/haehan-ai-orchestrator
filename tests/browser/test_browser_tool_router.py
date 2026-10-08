"""Browser Tool Router tests.

Tests for the Browser Tool Protocol router and policy enforcement.
"""

from __future__ import annotations

from pathlib import Path

from ai_orchestrator.browser_tool import backend_policy as policy
from ai_orchestrator.browser_tool.router import route_browser_task, route_browser_task_with_params
from ai_orchestrator.browser_tool.schemas import BrowserResult, BrowserTask


class TestBrowserTaskSchema:
    """BrowserTask dataclass tests."""

    def test_browser_task_creation(self):
        """Create a valid BrowserTask."""
        task = BrowserTask(action="inspect", params={"dry_run": True})
        assert task.action == "inspect"
        assert task.params == {"dry_run": True}

    def test_browser_task_with_defaults(self):
        """BrowserTask uses default empty params."""
        task = BrowserTask(action="inspect")
        assert task.params == {}
        assert task.timeout_seconds == 30
        assert task.approval_required is False


class TestBrowserResultSchema:
    """BrowserResult dataclass tests."""

    def test_browser_result_creation(self):
        """Create a valid BrowserResult."""
        result = BrowserResult(
            success=True,
            action="inspect",
            data={"url": "https://example.com"},
            backend="mock",
        )
        assert result.success is True
        assert result.action == "inspect"
        assert result.data["url"] == "https://example.com"
        assert result.error == ""
        assert result.error_code == ""


class TestBrowserToolPolicy:
    """Policy enforcement tests."""

    def test_inspect_action_policy(self):
        """browser.inspect has low risk and requires dry_run only."""
        policy_obj = policy.get_action_policy("inspect")
        assert policy_obj is not None
        assert policy_obj.risk_level == "low"
        assert policy_obj.requires_approval is False
        assert policy_obj.requires_dry_run is True
        assert policy_obj.blocked is False

    def test_execute_click_policy(self):
        """browser.execute_click is blocked in current stage."""
        policy_obj = policy.get_action_policy("execute_click")
        assert policy_obj is not None
        assert policy_obj.risk_level == "medium"
        assert policy_obj.requires_approval is True
        assert policy_obj.blocked is True
        assert policy_obj.blocked_reason == "actual_browser_execution_not_enabled"

    def test_unknown_action_policy(self):
        """Unknown action returns None policy."""
        policy_obj = policy.get_action_policy("unknown_action")  # type: ignore
        assert policy_obj is None

    def test_is_action_blocked(self):
        """Check action blocking status."""
        assert policy.is_action_blocked("inspect") is False
        assert policy.is_action_blocked("execute_click") is True
        assert policy.is_action_blocked("execute_type") is True
        assert policy.is_action_blocked("unknown") is False


class TestRouterInspectAction:
    """Router tests for browser.inspect."""

    def test_route_inspect_dry_run_true(self):
        """Route browser.inspect with dry_run=True."""
        task = BrowserTask(action="inspect", params={"dry_run": True})
        result = route_browser_task(task)

        assert result.success is True
        assert result.action == "inspect"
        assert result.data["dry_run"] is True
        assert result.data["browser_started"] is False
        assert result.data["title"] == "DRY_RUN_BROWSER_INSPECT"
        assert result.data["status"] == "ok"
        assert result.error == ""
        assert result.error_code == ""

    def test_route_inspect_dry_run_true_with_url(self):
        """Route browser.inspect with dry_run=True and URL."""
        task = BrowserTask(action="inspect", params={"dry_run": True, "url": "https://example.com"})
        result = route_browser_task(task)

        assert result.success is True
        assert result.data["url"] == "https://example.com"
        assert result.data["browser_started"] is False

    def test_route_inspect_dry_run_false(self):
        """Route browser.inspect with dry_run=False (blocked)."""
        task = BrowserTask(action="inspect", params={"dry_run": False})
        result = route_browser_task(task)

        assert result.success is False
        assert result.action == "inspect"
        assert result.data["dry_run"] is False
        assert result.data["browser_started"] is False
        assert result.data["reason"] == "actual_browser_execution_not_enabled"
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_route_inspect_no_dry_run_param(self):
        """Route browser.inspect without dry_run param (defaults to False, blocked)."""
        task = BrowserTask(action="inspect", params={})
        result = route_browser_task(task)

        assert result.success is False
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_route_inspect_dry_run_string_true(self):
        """Route browser.inspect with dry_run="true" (string coercion)."""
        task = BrowserTask(action="inspect", params={"dry_run": "true"})
        result = route_browser_task(task)

        assert result.success is True
        assert result.data["dry_run"] is True

    def test_route_inspect_dry_run_string_yes(self):
        """Route browser.inspect with dry_run="yes" (string coercion)."""
        task = BrowserTask(action="inspect", params={"dry_run": "yes"})
        result = route_browser_task(task)

        assert result.success is True
        assert result.data["dry_run"] is True


class TestRouterBlockedActions:
    """Router tests for blocked actions."""

    def test_route_execute_click_blocked(self):
        """browser.execute_click is blocked."""
        task = BrowserTask(action="execute_click", params={})
        result = route_browser_task(task)

        assert result.success is False
        assert result.error_code == "BROWSER_ACTION_BLOCKED"
        assert "blocked" in result.data or "reason" in result.data

    def test_route_execute_type_blocked(self):
        """browser.execute_type is blocked."""
        task = BrowserTask(action="execute_type", params={})
        result = route_browser_task(task)

        assert result.success is False
        assert result.error_code == "BROWSER_ACTION_BLOCKED"

    def test_route_plan_click_blocked(self):
        """browser.plan_click is blocked (not implemented)."""
        task = BrowserTask(action="plan_click", params={})
        result = route_browser_task(task)

        assert result.success is False
        assert result.error_code == "BROWSER_ACTION_BLOCKED"


class TestRouterUnknownAction:
    """Router tests for unknown actions."""

    def test_route_unknown_action(self):
        """Unknown action returns UNKNOWN_BROWSER_ACTION error."""
        task = BrowserTask(action="unknown_action", params={})  # type: ignore
        result = route_browser_task(task)

        assert result.success is False
        assert result.error_code == "UNKNOWN_BROWSER_ACTION"
        assert "unknown" in result.error.lower()


class TestRouterConvenienceFunction:
    """Tests for route_browser_task_with_params convenience function."""

    def test_route_with_params_inspect_dry_run(self):
        """Convenience function with inspect dry_run."""
        result = route_browser_task_with_params("inspect", {"dry_run": True})

        assert result.success is True
        assert result.data["dry_run"] is True

    def test_route_with_params_no_params(self):
        """Convenience function without params (empty dict)."""
        result = route_browser_task_with_params("inspect", None)

        assert result.success is False  # defaults to dry_run=False
        assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

    def test_route_with_params_unknown_action(self):
        """Convenience function with unknown action string."""
        result = route_browser_task_with_params("unknown_action", {})

        assert result.success is False
        assert result.error_code == "UNKNOWN_BROWSER_ACTION"


class TestNoPlaywrightImport:
    """Verify router has no Playwright dependencies."""

    def test_router_imports(self):
        """Browser tool router should not import playwright."""
        import ai_orchestrator.browser_tool.router as router_module

        source_file = router_module.__file__
        assert source_file is not None

        with Path(source_file).open(encoding="utf-8") as f:
            source = f.read()

        assert "from playwright" not in source
        assert "import playwright" not in source

    def test_mock_backend_imports(self):
        """Mock backend should not import playwright."""
        import ai_orchestrator.browser_tool.mock_backend as mock_module

        source_file = mock_module.__file__
        assert source_file is not None

        with Path(source_file).open(encoding="utf-8") as f:
            source = f.read()

        assert "from playwright" not in source
        assert "import playwright" not in source


class TestBrowserStartedInvariant:
    """Verify browser_started is always False."""

    def test_browser_started_dry_run_true(self):
        """browser_started=False for dry_run=True."""
        result = route_browser_task_with_params("inspect", {"dry_run": True})
        assert result.data.get("browser_started") is False

    def test_browser_started_dry_run_false(self):
        """browser_started=False for dry_run=False."""
        result = route_browser_task_with_params("inspect", {"dry_run": False})
        assert result.data.get("browser_started") is False
