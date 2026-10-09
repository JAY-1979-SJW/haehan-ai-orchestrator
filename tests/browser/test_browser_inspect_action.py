"""Tests for browser.inspect action handler."""

from pathlib import Path

import pytest

from core.agent_runtime.connection.actions import execute_action


def test_browser_inspect_registered():
    """Verify browser.inspect is registered in _ACTIONS."""
    from core.agent_runtime.connection.actions import _ACTIONS

    assert "browser.inspect" in _ACTIONS


def test_browser_inspect_dry_run_true():
    """Test browser.inspect with dry_run=True returns success mock response."""
    result = execute_action("browser.inspect", {"dry_run": True})

    assert result.success is True
    assert result.summary == "browser_inspect_dry_run_ok"
    assert result.data["action"] == "browser.inspect"
    assert result.data["dry_run"] is True
    assert result.data["browser_started"] is False
    assert result.data["title"] == "DRY_RUN_BROWSER_INSPECT"
    assert result.data["status"] == "ok"
    assert result.error_code == ""


def test_browser_inspect_dry_run_true_with_url():
    """Test browser.inspect with dry_run=True echoes URL if provided."""
    url = "https://example.com"
    result = execute_action("browser.inspect", {"dry_run": True, "url": url})

    assert result.success is True
    assert result.data["url"] == url


def test_browser_inspect_dry_run_true_without_url():
    """Test browser.inspect with dry_run=True returns None for URL if not provided."""
    result = execute_action("browser.inspect", {"dry_run": True})

    assert result.success is True
    assert result.data["url"] is None


def test_browser_inspect_dry_run_false():
    """Test browser.inspect with dry_run=False returns blocked response."""
    result = execute_action("browser.inspect", {"dry_run": False})

    assert result.success is False
    assert result.summary == "browser_inspect_blocked"
    assert result.data["action"] == "browser.inspect"
    assert result.data["dry_run"] is False
    assert result.data["browser_started"] is False
    assert result.data["reason"] == "actual_browser_execution_not_enabled"
    assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"


def test_browser_inspect_no_dry_run_param():
    """Test browser.inspect with no dry_run parameter (defaults to False)."""
    result = execute_action("browser.inspect", {})

    assert result.success is False
    assert result.summary == "browser_inspect_blocked"
    assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"


def test_browser_inspect_dry_run_string_true():
    """Test browser.inspect accepts dry_run as string true."""
    result = execute_action("browser.inspect", {"dry_run": "true"})

    assert result.success is True
    assert result.data["dry_run"] is True


def test_browser_inspect_dry_run_string_yes():
    """Test browser.inspect accepts dry_run as string yes."""
    result = execute_action("browser.inspect", {"dry_run": "yes"})

    assert result.success is True
    assert result.data["dry_run"] is True


def test_browser_inspect_dry_run_string_false():
    """Test browser.inspect rejects dry_run as string false."""
    result = execute_action("browser.inspect", {"dry_run": "false"})

    assert result.success is False
    assert result.error_code == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"


def test_browser_inspect_not_automation_import():
    """Verify browser_actions module does not import automation libraries."""
    with Path("core/agent_runtime/browser/browser_actions.py").open(encoding="utf-8") as f:
        content = f.read()

    # Check for common automation library imports
    assert "from subprocess import" not in content
    assert "import subprocess" not in content
    assert "asyncio.create_subprocess" not in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
