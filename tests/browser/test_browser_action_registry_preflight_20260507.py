"""Tests for Browser Action Registry Preflight Module."""

import json
from pathlib import Path

from ai_orchestrator.browser_tool.approval.approval_record_store import (
    append_approval_record,
    build_approval_decision,
    build_approval_request,
)
from ai_orchestrator.browser_tool.preflight.action_registry_preflight import (
    build_action_preflight_context,
    evaluate_action_registry_preflight,
    get_browser_action_policy,
    validate_action_preflight_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_action_registry_preflight_20260507.json"


class TestGetBrowserActionPolicy:
    """Test get_browser_action_policy()."""

    def test_inspect_policy(self):
        """browser.inspect has low risk, no approval required."""
        policy = get_browser_action_policy("browser.inspect")
        assert policy.get("operation_type") == "read"
        assert policy.get("risk_level") == "low"
        assert policy.get("approval_required") is False

    def test_open_url_controlled_policy(self):
        """browser.open_url_controlled requires approval."""
        policy = get_browser_action_policy("browser.open_url_controlled")
        assert policy.get("operation_type") == "open_url"
        assert policy.get("approval_required") is True
        assert policy.get("audit_required") is True

    def test_execute_type_policy(self):
        """browser.execute_type is blocked by default."""
        policy = get_browser_action_policy("browser.execute_type")
        assert policy.get("operation_type") == "type"
        assert policy.get("blocked_by_default") is True
        assert policy.get("block_reason") == "TYPE_BLOCKED"

    def test_unknown_action(self):
        """Unknown action returns empty policy."""
        policy = get_browser_action_policy("browser.unknown")
        assert policy == {}


class TestBuildActionPreflightContext:
    """Test build_action_preflight_context()."""

    def test_known_action(self):
        """Known action builds context with policy."""
        payload = {"action_name": "browser.inspect"}
        ctx = build_action_preflight_context(payload)

        assert ctx.get("action_name") == "browser.inspect"
        assert ctx.get("action_known") is True
        assert "registry_policy" in ctx

    def test_unknown_action(self):
        """Unknown action context is empty policy."""
        payload = {"action_name": "browser.unknown"}
        ctx = build_action_preflight_context(payload)

        assert ctx.get("action_known") is False


class TestEvaluateActionRegistryPreflight:
    """Test evaluate_action_registry_preflight()."""

    def test_inspect_allowed_dry_run(self):
        """browser.inspect read-only action allowed dry-run."""
        payload = {
            "workflow_run_id": "run_1",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "approval_required": False,
            "production_mode": False,
        }
        result = evaluate_action_registry_preflight(payload)

        assert result["preflight_decision"] == "ALLOW_DRY_RUN_DISPATCH"
        assert result["safe_to_execute"] is False
        assert result["safe_to_dispatch"] is True

    def test_unknown_action_blocked(self):
        """Unknown action is blocked."""
        payload = {
            "workflow_run_id": "run_1",
            "action_name": "browser.unknown",
        }
        result = evaluate_action_registry_preflight(payload)

        assert result["preflight_decision"] == "UNKNOWN_ACTION"
        assert result["block_reason"] == "ACTION_UNKNOWN"

    def test_type_always_blocked(self, tmp_path):
        """browser.execute_type is always blocked."""
        store_path = tmp_path / "approval.jsonl"

        # Create and approve an approval request
        req = build_approval_request(
            approval_id="appr_123",
            workflow_run_id="run_1",
            workflow_id="future_login",
            action_name="type_password",
            operation_type="type",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="t1",
            user_id="u1",
            site_id="s1",
        )
        append_approval_record(req, str(store_path))

        approved = build_approval_decision(
            approval_id="appr_123",
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin_1",
            decided_role="admin",
        )
        append_approval_record(approved, str(store_path))

        payload = {
            "workflow_run_id": "run_1",
            "action_name": "browser.execute_type",
            "approval_required": True,
            "approval_id": "appr_123",
            "tenant_id": "t1",
            "user_id": "u1",
            "site_id": "s1",
            "production_mode": False,
        }
        result = evaluate_action_registry_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "TYPE_BLOCKED"
        assert result["safe_to_execute"] is False

    def test_submit_denied_by_default(self):
        """Submit operation DENY_BY_DEFAULT (type operation in policy)."""
        payload = {
            "workflow_run_id": "run_1",
            "action_name": "browser.open_type_close_controlled",
            "approval_required": True,
            "tenant_id": "t1",
            "user_id": "u1",
            "site_id": "s1",
            "production_mode": False,
        }
        result = evaluate_action_registry_preflight(payload)

        # browser.open_type_close_controlled is treated as type operation (policy)
        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "TYPE_BLOCKED"

    def test_production_mode_blocked(self):
        """Production mode blocks action."""
        payload = {
            "workflow_run_id": "run_1",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "production_mode": True,
        }
        result = evaluate_action_registry_preflight(payload)

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "PRODUCTION_MODE_BLOCKED"

    def test_missing_action_name(self):
        """Missing action_name is blocked."""
        payload = {"workflow_run_id": "run_1"}
        result = evaluate_action_registry_preflight(payload)

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "ACTION_UNKNOWN"

    def test_safe_to_execute_always_false(self):
        """safe_to_execute is always false."""
        test_cases = [
            {"action_name": "browser.inspect"},
            {"action_name": "browser.plan_open_url"},
            {"action_name": "browser.execute_click"},
        ]

        for payload_base in test_cases:
            payload = {
                "workflow_run_id": "run_1",
                "production_mode": False,
                **payload_base,
            }
            result = evaluate_action_registry_preflight(payload)
            assert result["safe_to_execute"] is False


class TestValidateActionPreflightResult:
    """Test validate_action_preflight_result()."""

    def test_valid_result(self):
        """Valid result passes validation."""
        result = {
            "action_name": "browser.inspect",
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "safe_to_execute": False,
        }
        errors = validate_action_preflight_result(result)
        assert errors == []

    def test_safe_to_execute_must_be_false(self):
        """safe_to_execute=true fails validation."""
        result = {
            "action_name": "browser.inspect",
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "safe_to_execute": True,
        }
        errors = validate_action_preflight_result(result)
        assert any("safe_to_execute" in e for e in errors)

    def test_production_allowed_must_be_false(self):
        """production_allowed=true fails validation."""
        result = {
            "action_name": "browser.inspect",
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "safe_to_execute": False,
            "production_allowed": True,
        }
        errors = validate_action_preflight_result(result)
        assert any("production_allowed" in e for e in errors)


class TestFixtureCompatibility:
    """Test fixture compatibility."""

    def test_fixture_loads(self):
        """Fixture JSON loads successfully."""
        assert FIXTURE_PATH.exists(), f"Fixture not found: {FIXTURE_PATH}"
        with FIXTURE_PATH.open() as f:
            data = json.load(f)
        assert data["fixture_id"] == "BROWSER_ACTION_REGISTRY_PREFLIGHT_1"

    def test_fixture_cases_valid(self):
        """All fixture cases have expected structure."""
        with FIXTURE_PATH.open() as f:
            data = json.load(f)

        for case in data["cases"]:
            assert "case_id" in case
            assert "input" in case
            assert "expected" in case
            assert "action_name" in case

    def test_safe_to_execute_all_false_in_fixture(self):
        """All fixture cases have safe_to_execute=false."""
        with FIXTURE_PATH.open() as f:
            data = json.load(f)

        for case in data["cases"]:
            expected = case.get("expected", {})
            safe_exec = expected.get("safe_to_execute")
            if safe_exec is not None:
                assert safe_exec is False, f"Case {case['case_id']}: safe_to_execute should be false"


class TestRegistryPolicyConsistency:
    """Test consistency with existing registry."""

    def test_no_task_executor_import(self):
        """Module should not import task_executor."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.preflight import action_registry_preflight

        source = inspect.getsource(action_registry_preflight)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("task_executor" in imp for imp in imports)

    def test_no_dispatcher_import(self):
        """Module should not import dispatcher."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.preflight import action_registry_preflight

        source = inspect.getsource(action_registry_preflight)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("dispatcher" in imp for imp in imports)

    def test_no_browser_execution_import(self):
        """Module should not import actual browser execution."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.preflight import action_registry_preflight

        source = inspect.getsource(action_registry_preflight)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("playwright" in imp for imp in imports)
