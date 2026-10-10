"""Tests for Browser Allowlist Preflight Module."""

import json
from pathlib import Path

from ai_orchestrator.browser_tool.preflight.allowlist_preflight import (
    build_allowlist_context,
    evaluate_allowlist_preflight,
    normalize_url_for_policy,
    validate_allowlist_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_allowlist_preflight_20260507.json"


class TestNormalizeUrlForPolicy:
    """Test normalize_url_for_policy()."""

    def test_valid_url(self):
        """Valid URL is normalized."""
        url = "https://example.com/path?query=value"
        result = normalize_url_for_policy(url)

        assert result["domain"] == "example.com"
        assert result["path"] == "/path"
        assert result["query"] == "query=value"
        assert result["url_hash"]
        assert "example.com" in result["url_redacted"]

    def test_empty_url(self):
        """Empty URL returns empty result."""
        result = normalize_url_for_policy("")
        assert result["domain"] == ""
        assert result["path"] == ""

    def test_sensitive_params_detected(self):
        """Sensitive query params are detected."""
        url = "https://example.com/login?password=secret&user=john"
        result = normalize_url_for_policy(url)

        assert result["has_sensitive_params"] is True
        assert "secret" not in result["url_redacted"]


class TestBuildAllowlistContext:
    """Test build_allowlist_context()."""

    def test_url_context(self):
        """URL context is built."""
        payload = {
            "target_url": "https://example.com/page",
            "target_domain": "example.com",
            "target_path": "/page",
        }
        ctx = build_allowlist_context(payload)

        assert ctx["target_domain"] == "example.com"
        assert ctx["target_path"] == "/page"
        assert ctx["target_url_hash"]


class TestEvaluateAllowlistPreflight:
    """Test evaluate_allowlist_preflight()."""

    def test_read_no_allowlist(self):
        """Read operation does not require allowlist."""
        payload = {
            "action_name": "browser.inspect",
            "operation_type": "read",
            "target_domain": "any.com",
            "allowlist_required": False,
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["allowlist_decision"] == "ALLOW_DRY_RUN"
        assert result["safe_to_execute"] is False
        assert result["safe_to_dispatch"] is True

    def test_allowed_domain(self):
        """Allowed domain allows action."""
        payload = {
            "action_name": "browser.open_url_controlled",
            "operation_type": "open_url",
            "target_domain": "example.com",
            "target_url": "https://example.com/page",
            "allowlist_required": True,
            "tenant_id": "t1",
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["domain_allowed"] is True
        assert result["safe_to_dispatch"] is True

    def test_blocked_domain(self):
        """Blocked domain is denied."""
        payload = {
            "action_name": "browser.open_url_controlled",
            "operation_type": "open_url",
            "target_domain": "localhost",
            "allowlist_required": True,
            "tenant_id": "t1",
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["allowlist_decision"] == "BLOCK"
        assert result["block_reason"] == "DOMAIN_BLOCKED"

    def test_missing_domain(self):
        """Missing domain is blocked."""
        payload = {
            "action_name": "browser.open_url_controlled",
            "operation_type": "open_url",
            "target_domain": "",
            "allowlist_required": True,
            "tenant_id": "t1",
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["block_reason"] == "TARGET_DOMAIN_MISSING"

    def test_type_operation_blocked(self):
        """Type operation is always blocked."""
        payload = {
            "action_name": "browser.execute_type",
            "operation_type": "type",
            "target_domain": "example.com",
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["allowlist_decision"] == "BLOCK"
        assert result["block_reason"] == "TYPE_BLOCKED"

    def test_submit_operation_denied(self):
        """Submit operation DENY_BY_DEFAULT."""
        payload = {
            "action_name": "browser.open_type_close_controlled",
            "operation_type": "submit",
            "target_domain": "example.com",
            "production_mode": False,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["block_reason"] == "SUBMIT_DENY_BY_DEFAULT"

    def test_production_mode_blocked(self):
        """Production mode blocks action."""
        payload = {
            "action_name": "browser.inspect",
            "operation_type": "read",
            "target_domain": "example.com",
            "production_mode": True,
        }
        result = evaluate_allowlist_preflight(payload)

        assert result["block_reason"] == "PRODUCTION_MODE_BLOCKED"

    def test_safe_to_execute_always_false(self):
        """safe_to_execute is always false."""
        test_cases = [
            {
                "action_name": "browser.inspect",
                "operation_type": "read",
                "target_domain": "example.com",
            },
            {
                "action_name": "browser.open_url_controlled",
                "operation_type": "open_url",
                "target_domain": "example.com",
            },
        ]

        for payload_base in test_cases:
            payload = {
                "production_mode": False,
                **payload_base,
            }
            result = evaluate_allowlist_preflight(payload)
            assert result["safe_to_execute"] is False


class TestValidateAllowlistResult:
    """Test validate_allowlist_result()."""

    def test_valid_result(self):
        """Valid result passes validation."""
        result = {
            "allowlist_decision": "ALLOW_DRY_RUN",
            "safe_to_execute": False,
        }
        errors = validate_allowlist_result(result)
        assert errors == []

    def test_safe_to_execute_must_be_false(self):
        """safe_to_execute=true fails validation."""
        result = {
            "allowlist_decision": "ALLOW_DRY_RUN",
            "safe_to_execute": True,
        }
        errors = validate_allowlist_result(result)
        assert any("safe_to_execute" in e for e in errors)


class TestFixtureCompatibility:
    """Test fixture."""

    def test_fixture_loads(self):
        """Fixture loads successfully."""
        assert FIXTURE_PATH.exists()
        with FIXTURE_PATH.open() as f:
            data = json.load(f)
        assert data["fixture_id"] == "BROWSER_ALLOWLIST_PREFLIGHT_1"

    def test_fixture_cases_valid(self):
        """Fixture cases are valid."""
        with FIXTURE_PATH.open() as f:
            data = json.load(f)

        for case in data["cases"]:
            assert "case_id" in case
            assert "input" in case
            assert "expected" in case


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_task_executor_import(self):
        """Module should not import task_executor."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.preflight import allowlist_preflight

        source = inspect.getsource(allowlist_preflight)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("task_executor" in imp for imp in imports)
        assert not any("dispatcher" in imp for imp in imports)
        assert not any("playwright" in imp for imp in imports)
