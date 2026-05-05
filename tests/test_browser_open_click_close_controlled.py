"""Mock tests for browser.open_click_close_controlled action."""
import os
import sys
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.local_agent_client import _handle_browser_open_click_close_controlled


class TestBrowserOpenClickCloseControlled:
    """Test browser.open_click_close_controlled action."""

    def setup_method(self):
        """Setup for each test: enable browser execution."""
        os.environ["BROWSER_EXECUTION_ENABLED"] = "true"

    def teardown_method(self):
        """Cleanup after each test."""
        os.environ.pop("BROWSER_EXECUTION_ENABLED", None)
        os.environ.pop("BROWSER_ACTUAL_CLICK", None)

    def test_basic_success(self):
        """Test basic success case with default target_id."""
        task = {
            "task_id": "test_001",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        assert result["summary"] == "browser_open_click_close_controlled_ok"
        assert result["data"]["action"] == "browser.open_click_close_controlled"
        assert result["data"]["status"] == "ok"
        assert result["data"]["execution_mode"] == "isolated_sample_click"
        assert result["data"]["approval_required"] is True

    def test_success_with_primary_action(self):
        """Test with explicit sample_primary_action."""
        task = {
            "task_id": "test_002",
            "params": {"target_id": "sample_primary_action"},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        assert result["data"]["clicked_target"]["target_id"] == "sample_primary_action"
        assert result["data"]["clicked_target"]["target_role"] == "primary_action"
        assert result["data"]["clicked_target"]["selector_redacted"] is True

    def test_success_with_secondary_action(self):
        """Test with sample_secondary_action."""
        task = {
            "task_id": "test_003",
            "params": {"target_id": "sample_secondary_action"},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        assert result["data"]["clicked_target"]["target_id"] == "sample_secondary_action"
        assert result["data"]["clicked_target"]["target_role"] == "secondary_action"

    def test_invalid_target_id(self):
        """Test with invalid target_id (not in enum)."""
        task = {
            "task_id": "test_004",
            "params": {"target_id": "malicious_target"},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False
        assert result["summary"] == "browser_open_click_close_controlled_invalid_params"
        assert result["data"]["status"] == "error_invalid_target_id"

    def test_forbidden_selector_key(self):
        """Test with forbidden selector key."""
        task = {
            "task_id": "test_005",
            "params": {
                "target_id": "sample_primary_action",
                "selector": "button.primary",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False
        assert result["summary"] == "browser_open_click_close_controlled_invalid_params"

    def test_forbidden_css_selector_key(self):
        """Test with forbidden css_selector key."""
        task = {
            "task_id": "test_006",
            "params": {
                "css_selector": ".button",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_xpath_key(self):
        """Test with forbidden xpath key."""
        task = {
            "task_id": "test_007",
            "params": {
                "xpath": "//button[@id='primary']",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_coordinates_key(self):
        """Test with forbidden coordinates key."""
        task = {
            "task_id": "test_008",
            "params": {
                "x": 100,
                "y": 200,  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_url_key(self):
        """Test with forbidden url key (user URL)."""
        task = {
            "task_id": "test_009",
            "params": {
                "url": "https://attacker.com/",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_dom_key(self):
        """Test with forbidden dom key."""
        task = {
            "task_id": "test_010",
            "params": {
                "dom": "<html>...</html>",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_screenshot_key(self):
        """Test with forbidden screenshot key."""
        task = {
            "task_id": "test_011",
            "params": {
                "screenshot": "base64_encoded_data",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_forbidden_cookie_key(self):
        """Test with forbidden cookie key."""
        task = {
            "task_id": "test_012",
            "params": {
                "cookie": "session=abc123",  # forbidden
            },
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False

    def test_result_redaction_no_raw_url(self):
        """Test that result doesn't contain raw URL."""
        task = {
            "task_id": "test_013",
            "params": {"target_id": "sample_primary_action"},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]

        # Check that raw URL fields are not in result
        assert "url" not in data
        assert "raw_url" not in data
        assert "page_title" not in data
        assert "hostname" not in data
        assert "path" not in data
        assert "query" not in data

    def test_result_redaction_no_raw_selector(self):
        """Test that result doesn't contain raw selector."""
        task = {
            "task_id": "test_014",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]
        clicked_target = data.get("clicked_target", {})

        # Check that raw selector fields are not in result
        assert "selector" not in clicked_target
        assert "css_selector" not in clicked_target
        assert "xpath" not in clicked_target
        assert "coordinates" not in clicked_target
        assert "x" not in clicked_target
        assert "y" not in clicked_target

    def test_result_contains_url_redacted(self):
        """Test that result contains url_redacted=true."""
        task = {
            "task_id": "test_015",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        url_info = result["data"].get("url_info", {})
        assert url_info.get("url_redacted") is True

    def test_result_contains_selector_redacted(self):
        """Test that result contains selector_redacted=true."""
        task = {
            "task_id": "test_016",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        clicked_target = result["data"].get("clicked_target", {})
        assert clicked_target.get("selector_redacted") is True

    def test_result_no_dom_or_html(self):
        """Test that result doesn't contain DOM or HTML."""
        task = {
            "task_id": "test_017",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]
        assert "dom" not in data
        assert "html" not in data
        assert "innerHTML" not in data

    def test_result_no_screenshot(self):
        """Test that result doesn't contain screenshot."""
        task = {
            "task_id": "test_018",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]
        assert "screenshot" not in data
        assert "screenshot_path" not in data
        assert "screenshot_data" not in data

    def test_result_no_sensitive_data(self):
        """Test that result doesn't contain sensitive data."""
        task = {
            "task_id": "test_019",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]
        assert "cookie" not in data
        assert "session" not in data
        assert "localStorage" not in data
        assert "profile_path" not in data
        assert "browser_pid" not in data

    def test_invalid_params_type(self):
        """Test with invalid params type (not dict)."""
        task = {
            "task_id": "test_020",
            "params": "not_a_dict",
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False
        assert result["summary"] == "browser_open_click_close_controlled_invalid_params"

    def test_disabled_without_env_flag(self):
        """Test that action is disabled without BROWSER_EXECUTION_ENABLED."""
        # Remove env flags to simulate disabled state
        os.environ.pop("BROWSER_EXECUTION_ENABLED", None)
        os.environ.pop("BROWSER_ACTUAL_CLICK", None)

        task = {
            "task_id": "test_021",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is False
        assert result["summary"] == "browser_open_click_close_controlled_disabled"
        assert result["data"]["approval_required"] is True

    def test_result_structure_contains_required_fields(self):
        """Test that successful result has all required fields."""
        task = {
            "task_id": "test_022",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        data = result["data"]

        # Check required fields
        assert "action" in data
        assert "status" in data
        assert "execution_mode" in data
        assert "approval_required" in data
        assert "clicked_target" in data
        assert "url_info" in data
        assert "navigation" in data
        assert "browser" in data
        assert "cleanup" in data

    def test_browser_metadata_isolated_context(self):
        """Test that browser metadata shows isolated_context=true."""
        task = {
            "task_id": "test_023",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        browser = result["data"].get("browser", {})
        assert browser.get("isolated_context") is True
        assert browser.get("used_existing_profile") is False

    def test_browser_metadata_cleanup(self):
        """Test that browser metadata shows cleanup completed."""
        task = {
            "task_id": "test_024",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        cleanup = result["data"].get("cleanup", {})
        assert cleanup.get("context_closed") is True
        assert cleanup.get("browser_closed") is True
        assert cleanup.get("temp_files_deleted") is True

    def test_navigation_will_not_navigate(self):
        """Test that navigation shows will_navigate=false."""
        task = {
            "task_id": "test_025",
            "params": {},
        }
        result = _handle_browser_open_click_close_controlled(task)

        assert result["success"] is True
        navigation = result["data"].get("navigation", {})
        assert navigation.get("will_navigate") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
