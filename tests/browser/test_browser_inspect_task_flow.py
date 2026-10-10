"""Tests for browser.inspect action in task context (mock flow)."""
import sys

import pytest

sys.path.insert(0, '.')

from core.agent_runtime.agent import execute_local


def test_browser_inspect_dry_run_task():
    """Test browser.inspect dry_run action through execute_local."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": True, "url": "https://example.com"}
    )
    
    assert result["success"] is True
    assert result["error_code"] == ""
    assert result["data"]["action"] == "browser.inspect"
    assert result["data"]["dry_run"] is True
    assert result["data"]["browser_started"] is False
    assert result["data"]["url"] == "https://example.com"
    assert result["data"]["status"] == "ok"


def test_browser_inspect_dry_run_no_url():
    """Test browser.inspect dry_run without URL."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": True}
    )
    
    assert result["success"] is True
    assert result["data"]["url"] is None


def test_browser_inspect_actual_execution_blocked():
    """Test browser.inspect with dry_run=False is safely blocked."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": False}
    )
    
    assert result["success"] is False
    assert result["error_code"] == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"
    assert result["data"]["browser_started"] is False
    assert result["data"]["reason"] == "actual_browser_execution_not_enabled"


def test_browser_inspect_no_dry_run_param_blocked():
    """Test browser.inspect without dry_run param is blocked."""
    result = execute_local(
        "browser.inspect",
        {}
    )
    
    assert result["success"] is False
    assert result["error_code"] == "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"


def test_browser_inspect_dry_run_string_true():
    """Test browser.inspect accepts string 'true' for dry_run."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": "true"}
    )
    
    assert result["success"] is True
    assert result["data"]["dry_run"] is True


def test_browser_inspect_dry_run_string_yes():
    """Test browser.inspect accepts string 'yes' for dry_run."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": "yes"}
    )
    
    assert result["success"] is True
    assert result["data"]["dry_run"] is True


def test_browser_inspect_not_unknown_action():
    """Verify browser.inspect is registered and not UNKNOWN_ACTION."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": True}
    )
    
    # Must not be UNKNOWN_ACTION
    assert result["error_code"] != "UNKNOWN_ACTION"
    assert result["success"] is True


def test_browser_inspect_result_schema():
    """Verify result follows standard schema."""
    result = execute_local(
        "browser.inspect",
        {"dry_run": True}
    )
    
    # Check all required fields
    assert "success" in result
    assert "summary" in result
    assert "data" in result
    assert "error" in result
    assert "error_code" in result
    
    # Verify types
    assert isinstance(result["success"], bool)
    assert isinstance(result["summary"], str)
    assert isinstance(result["data"], dict)
    assert isinstance(result["error"], str)
    assert isinstance(result["error_code"], str)


def test_unknown_action_still_blocked():
    """Verify unknown actions are still properly rejected."""
    result = execute_local(
        "nonexistent_action_xyz",
        {}
    )
    
    assert result["success"] is False
    assert result["error_code"] == "UNKNOWN_ACTION"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
