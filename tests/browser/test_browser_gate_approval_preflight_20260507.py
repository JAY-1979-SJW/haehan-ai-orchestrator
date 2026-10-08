"""Tests for Browser Gate Approval Preflight Module.

Tests approval preflight evaluation before dispatch.
Uses temporary JSONL approval store for each test.
"""

import json

from ai_orchestrator.browser_tool.approval.approval_record_store import (
    append_approval_record,
    build_approval_decision,
    build_approval_request,
)
from ai_orchestrator.browser_tool.preflight.gate_approval_preflight import (
    build_gate_approval_context,
    evaluate_gate_approval_preflight,
    validate_gate_approval_result,
)


class TestBuildGateApprovalContext:
    """Test build_gate_approval_context()."""

    def test_no_approval_id(self, tmp_path):
        """If no approval_id, return empty dict."""
        payload = {"workflow_id": "test_wf"}
        ctx = build_gate_approval_context(payload, str(tmp_path / "approval.jsonl"))
        assert ctx == {}

    def test_approval_store_not_found(self, tmp_path):
        """If approval store doesn't exist, return empty dict."""
        payload = {"approval_id": "appr_123"}
        ctx = build_gate_approval_context(payload, str(tmp_path / "nonexistent.jsonl"))
        assert ctx == {}

    def test_approval_id_not_in_store(self, tmp_path):
        """If approval_id not in store, return empty dict."""
        store_path = tmp_path / "approval.jsonl"
        payload = {"approval_id": "appr_xyz"}
        ctx = build_gate_approval_context(payload, str(store_path))
        assert ctx == {}

    def test_approval_found(self, tmp_path):
        """Return approval context if found."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_001"

        # Create approval request
        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_notice",
            action_name="navigate",
            operation_type="open_url",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
            target_domain="g2b.gov.kr",
        )
        append_approval_record(req, str(store_path))

        # Query context
        payload = {"approval_id": approval_id}
        ctx = build_gate_approval_context(payload, str(store_path))

        assert ctx.get("approval_id") == approval_id
        assert ctx.get("approval_status") == "PENDING"


class TestEvaluateGateApprovalPreflight:
    """Test evaluate_gate_approval_preflight()."""

    def test_no_approval_required_read(self):
        """approval_required=false + read → ALLOW_DRY_RUN_DISPATCH."""
        payload = {
            "workflow_run_id": "run_123",
            "workflow_id": "test_wf",
            "action_name": "read_text",
            "operation_type": "read",
            "approval_required": False,
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "ALLOW_DRY_RUN_DISPATCH"
        assert result["safe_to_execute"] is False
        assert result["safe_to_dispatch"] is True

    def test_approval_required_missing_approval_id(self):
        """approval_required=true + approval_id missing → REQUIRE_APPROVAL."""
        payload = {
            "workflow_run_id": "run_123",
            "workflow_id": "test_wf",
            "action_name": "download",
            "operation_type": "read",
            "approval_required": True,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "REQUIRE_APPROVAL"
        assert result["block_reason"] == "APPROVAL_MISSING"
        assert result["safe_to_dispatch"] is False

    def test_approval_required_missing_context(self):
        """approval_required=true + missing context → BLOCK."""
        # Missing tenant_id
        payload = {
            "workflow_run_id": "run_123",
            "approval_required": True,
            "user_id": "user_1",
            "site_id": "site_1",
        }
        result = evaluate_gate_approval_preflight(payload)
        assert result["block_reason"] == "TENANT_CONTEXT_MISSING"
        assert result["preflight_decision"] == "BLOCK"

        # Missing user_id
        payload = {
            "workflow_run_id": "run_123",
            "approval_required": True,
            "tenant_id": "tenant_1",
            "site_id": "site_1",
        }
        result = evaluate_gate_approval_preflight(payload)
        assert result["block_reason"] == "USER_CONTEXT_MISSING"

        # Missing site_id
        payload = {
            "workflow_run_id": "run_123",
            "approval_required": True,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
        }
        result = evaluate_gate_approval_preflight(payload)
        assert result["block_reason"] == "SITE_CONTEXT_MISSING"

    def test_submit_always_deny_by_default(self):
        """submit operation → DENY_BY_DEFAULT (even without approval check)."""
        payload = {
            "workflow_run_id": "run_123",
            "workflow_id": "test_wf",
            "action_name": "submit_form",
            "operation_type": "submit",
            "approval_required": False,
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "DENY_BY_DEFAULT"
        assert result["block_reason"] == "SUBMIT_DENY_BY_DEFAULT"

    def test_type_always_blocked(self):
        """type operation → BLOCK (regardless of approval)."""
        payload = {
            "workflow_run_id": "run_123",
            "workflow_id": "test_wf",
            "action_name": "type_text",
            "operation_type": "type",
            "approval_required": False,
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "TYPE_BLOCKED"

    def test_production_mode_blocked(self):
        """production_mode=true → BLOCK."""
        payload = {
            "workflow_run_id": "run_123",
            "workflow_id": "test_wf",
            "operation_type": "read",
            "approval_required": False,
            "production_mode": True,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "PRODUCTION_MODE_BLOCKED"

    def test_gate_decision_block(self):
        """gate_decision=BLOCK → BLOCK."""
        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "gate_decision": "BLOCK",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "GATE_BLOCKED"

    def test_gate_decision_deny_by_default(self):
        """gate_decision=DENY_BY_DEFAULT → DENY_BY_DEFAULT."""
        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "gate_decision": "DENY_BY_DEFAULT",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["preflight_decision"] == "DENY_BY_DEFAULT"

    def test_approval_pending(self, tmp_path):
        """approval_status=PENDING → REQUIRE_APPROVAL."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_pending"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_attachment",
            action_name="download_plan",
            operation_type="read",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "REQUIRE_APPROVAL"
        assert result["block_reason"] == "APPROVAL_PENDING"
        assert result["approval_status"] == "PENDING"
        assert result["approval_found"] is True

    def test_approval_rejected(self, tmp_path):
        """approval_status=REJECTED → BLOCK."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_rejected"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_attachment",
            action_name="download_plan",
            operation_type="read",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        reject = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_REJECTED",
            decided_by="admin_1",
            decided_role="admin",
            decision_reason="Not allowed",
        )
        append_approval_record(reject, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "APPROVAL_REJECTED"
        assert result["approval_status"] == "REJECTED"

    def test_approval_expired(self, tmp_path):
        """approval_status=EXPIRED → BLOCK."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_expired"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_attachment",
            action_name="download_plan",
            operation_type="read",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        expired = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_EXPIRED",
            decided_by="system",
            decided_role="system",
        )
        append_approval_record(expired, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "APPROVAL_EXPIRED"
        assert result["approval_status"] == "EXPIRED"

    def test_approval_revoked(self, tmp_path):
        """approval_status=REVOKED → BLOCK."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_revoked"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_attachment",
            action_name="download_plan",
            operation_type="read",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        revoked = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_REVOKED",
            decided_by="admin_1",
            decided_role="admin",
            decision_reason="Revoked by admin",
        )
        append_approval_record(revoked, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "APPROVAL_REVOKED"
        assert result["approval_status"] == "REVOKED"

    def test_approval_approved_safe_to_execute_stays_false(self, tmp_path):
        """approval=APPROVED → safe_to_execute stays false (policy enforcement)."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_approved"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_attachment",
            action_name="download_plan",
            operation_type="read",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        approved = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin_1",
            decided_role="admin",
            decision_reason="Approved",
        )
        append_approval_record(approved, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        # Even with approval, safe_to_execute must be false
        assert result["safe_to_execute"] is False
        assert result["approval_status"] == "APPROVED"

    def test_approval_approved_open_url_allows_dispatch(self, tmp_path):
        """approval=APPROVED + open_url → safe_to_dispatch=true."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_approved_2"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="g2b_notice_detail",
            action_name="open_url",
            operation_type="open_url",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        approved = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin_1",
            decided_role="admin",
        )
        append_approval_record(approved, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "open_url",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "ALLOW_DRY_RUN_DISPATCH"
        assert result["safe_to_dispatch"] is True
        assert result["safe_to_execute"] is False

    def test_submit_blocks_even_with_approval(self, tmp_path):
        """submit + APPROVED → DENY_BY_DEFAULT."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_submit_block"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="future_submit",
            action_name="submit_form",
            operation_type="submit",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        approved = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin_1",
            decided_role="admin",
        )
        append_approval_record(approved, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "submit",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "DENY_BY_DEFAULT"
        assert result["block_reason"] == "SUBMIT_DENY_BY_DEFAULT"

    def test_type_blocks_even_with_approval(self, tmp_path):
        """type + APPROVED → BLOCK."""
        store_path = tmp_path / "approval.jsonl"
        approval_id = "appr_test_type_block"

        req = build_approval_request(
            approval_id=approval_id,
            workflow_run_id="run_123",
            workflow_id="future_login",
            action_name="type_password",
            operation_type="type",
            requested_by="user_1",
            requested_role="operator",
            tenant_id="tenant_1",
            user_id="user_1",
            site_id="site_1",
        )
        append_approval_record(req, str(store_path))

        approved = build_approval_decision(
            approval_id=approval_id,
            approval_event_type="APPROVAL_GRANTED",
            decided_by="admin_1",
            decided_role="admin",
        )
        append_approval_record(approved, str(store_path))

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "type",
            "approval_required": True,
            "approval_id": approval_id,
            "tenant_id": "tenant_1",
            "user_id": "user_1",
            "site_id": "site_1",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        assert result["preflight_decision"] == "BLOCK"
        assert result["block_reason"] == "TYPE_BLOCKED"

    def test_should_write_audit_on_block(self):
        """should_write_audit=true on block."""
        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "submit",
            "production_mode": False,
        }
        result = evaluate_gate_approval_preflight(payload)

        assert result["should_write_audit"] is True

    def test_safe_to_execute_always_false(self):
        """safe_to_execute always false (all cases)."""
        test_cases = [
            {"operation_type": "read", "approval_required": False},
            {"operation_type": "open_url", "approval_required": False},
            {"operation_type": "click", "approval_required": False},
            {"operation_type": "submit", "approval_required": False},
        ]

        for payload_base in test_cases:
            payload = {
                "workflow_run_id": "run_123",
                "production_mode": False,
                **payload_base,
            }
            result = evaluate_gate_approval_preflight(payload)
            assert result["safe_to_execute"] is False, f"Failed for {payload_base}"

    def test_no_sensitive_data_in_result(self, tmp_path):
        """Result should not contain raw passwords/tokens/secrets."""
        store_path = tmp_path / "approval.jsonl"

        payload = {
            "workflow_run_id": "run_123",
            "operation_type": "read",
            "approval_required": False,
            "production_mode": False,
            # Sensitive values (should not leak into result)
            "password": "secret123",
            "token": "abcdef123456",
            "secret": "mysecret",
        }
        result = evaluate_gate_approval_preflight(payload, str(store_path))

        # Result should not contain raw values
        result_str = json.dumps(result)
        assert "secret123" not in result_str
        assert "abcdef123456" not in result_str
        assert "mysecret" not in result_str

    def test_no_forbidden_imports(self):
        """gate_approval_preflight should not import task_executor, dispatcher, etc."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.preflight import gate_approval_preflight

        # Get source code
        source = inspect.getsource(gate_approval_preflight)
        tree = ast.parse(source)

        # Check imports
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        forbidden = {"task_executor", "dispatcher", "action_registry", "browser"}
        found = [imp for imp in imports if any(f in imp for f in forbidden)]  # noqa: F841

        # Only "browser_tool" should be present, not actual execution modules
        assert not any("task_executor" in imp for imp in imports)
        assert not any("dispatcher" in imp for imp in imports)
        assert not any("action_registry" in imp for imp in imports)
        # browser imports should be only approval/audit modules
        browser_imports = [imp for imp in imports if "browser" in imp]
        for imp in browser_imports:
            assert any(x in imp for x in ["approval_record", "workflow_audit", "gate_approval"])


class TestValidateGateApprovalResult:
    """Test validate_gate_approval_result()."""

    def test_valid_result(self):
        """Valid result passes validation."""
        result = {
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "approval_status": "NOT_FOUND",
            "safe_to_execute": False,
        }
        errors = validate_gate_approval_result(result)
        assert errors == []

    def test_missing_preflight_decision(self):
        """Missing preflight_decision fails."""
        result = {
            "approval_status": "NOT_FOUND",
            "safe_to_execute": False,
        }
        errors = validate_gate_approval_result(result)
        assert any("preflight_decision" in e for e in errors)

    def test_invalid_preflight_decision(self):
        """Invalid preflight_decision fails."""
        result = {
            "preflight_decision": "INVALID",
            "approval_status": "NOT_FOUND",
            "safe_to_execute": False,
        }
        errors = validate_gate_approval_result(result)
        assert any("preflight_decision" in e for e in errors)

    def test_safe_to_execute_must_be_false(self):
        """safe_to_execute=true fails."""
        result = {
            "preflight_decision": "ALLOW_DRY_RUN_DISPATCH",
            "approval_status": "NOT_FOUND",
            "safe_to_execute": True,
        }
        errors = validate_gate_approval_result(result)
        assert any("safe_to_execute" in e for e in errors)

    def test_block_decision_requires_reason(self):
        """BLOCK decision requires block_reason."""
        result = {
            "preflight_decision": "BLOCK",
            "approval_status": "NOT_FOUND",
            "safe_to_execute": False,
            "block_reason": None,
        }
        errors = validate_gate_approval_result(result)
        assert any("block_reason" in e for e in errors)

    def test_block_decision_with_valid_reason(self):
        """BLOCK with valid block_reason passes."""
        result = {
            "preflight_decision": "BLOCK",
            "approval_status": "NOT_FOUND",
            "safe_to_execute": False,
            "block_reason": "SUBMIT_DENY_BY_DEFAULT",
        }
        errors = validate_gate_approval_result(result)
        assert errors == []
