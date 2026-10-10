"""Tests for WebSocket payload schema formalization (BROWSER-4G).

Verifies:
1. Input payload validation (required fields, action types)
2. Output result schema safety (no secrets)
3. Token transmission rules
4. Whitelist/schema consistency
5. Metadata constraints
6. Status vocabulary
"""

import pytest

from ai_orchestrator.agent_hub.registry import facade as _reg
from core.agent_runtime.browser.bridge.browser_websocket_schema import (
    ALLOWED_ACTION_TYPES,
    RESULT_DATA_ALLOWED_KEYS,
    RESULT_DATA_FORBIDDEN_KEYS,
    VALID_TASK_STATUS,
    BrowserWebSocketTaskPayloadSchema,
    BrowserWebSocketTaskResultSchema,
    validate_payload_schema,
    validate_result_schema,
)


class TestPayloadValidation:
    """Validate input payload schema"""

    def test_valid_execute_click_payload_validates(self):
        """Valid execute_click payload passes validation"""
        data = {
            "task_id": "task-001",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#increment-btn",
            "approval_id": "appr-001",
            "approval_token": "token-xyz",
        }

        is_valid, error = validate_payload_schema(data)
        assert is_valid is True
        assert error is None

    def test_valid_execute_type_payload_validates(self):
        """Valid execute_type payload with value passes validation"""
        data = {
            "task_id": "task-002",
            "task_type": "browser_action",
            "action_type": "browser.execute_type",
            "selector": "#search-input",
            "value": "typed text",
            "approval_id": "appr-002",
            "approval_token": "token-abc",
        }

        is_valid, error = validate_payload_schema(data)
        assert is_valid is True
        assert error is None

    def test_valid_plan_payload_validates(self):
        """Valid plan_click payload passes validation"""
        data = {
            "task_id": "task-003",
            "task_type": "browser_action",
            "action_type": "browser.plan_click",
            "selector": "#btn",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is True

    def test_execute_submit_payload_rejected(self):
        """execute_submit action is explicitly blocked"""
        data = {
            "task_id": "task-004",
            "task_type": "browser_action",
            "action_type": "browser.execute_submit",
            "selector": "#submit-btn",
        }

        is_valid, error = validate_payload_schema(data)
        assert is_valid is False
        assert "blocked" in error.lower()

    def test_unsupported_action_type_rejected(self):
        """Unsupported action types are rejected"""
        data = {
            "task_id": "task-005",
            "task_type": "browser_action",
            "action_type": "browser.delete_all",
            "selector": "#btn",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is False

    def test_missing_task_id_rejected(self):
        """Payload without task_id rejected"""
        data = {
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is False

    def test_wrong_task_type_value_rejected(self):
        """Payload with wrong task_type value rejected"""
        data = {
            "task_id": "task-006",
            "task_type": "http_request",
            "action_type": "browser.execute_click",
            "selector": "#btn",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is False

    def test_missing_action_type_rejected(self):
        """Payload without action_type rejected"""
        data = {
            "task_id": "task-008",
            "task_type": "browser_action",
            "selector": "#btn",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is False

    def test_missing_selector_rejected(self):
        """Payload without selector rejected"""
        data = {
            "task_id": "task-009",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is False

    def test_execute_type_without_value_rejected(self):
        """execute_type without value rejected"""
        data = {
            "task_id": "task-010",
            "task_type": "browser_action",
            "action_type": "browser.execute_type",
            "selector": "#input",
        }

        is_valid, error = validate_payload_schema(data)
        assert is_valid is False
        assert "value" in error.lower()


class TestApprovalTokenHandling:
    """Verify approval token transmission rules"""

    def test_approval_token_allowed_in_input_payload(self):
        """approval_token is allowed in input payload"""
        data = {
            "task_id": "task-011",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "approval_token": "secret-token-value",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is True

    def test_final_approval_token_allowed_in_input_payload(self):
        """final_approval_token is allowed in input payload"""
        data = {
            "task_id": "task-012",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "final_approval_token": "final-token-value",
        }

        is_valid, _error = validate_payload_schema(data)
        assert is_valid is True

    def test_approval_token_not_in_safe_dict(self):
        """approval_token removed from safe_dict"""
        schema = BrowserWebSocketTaskPayloadSchema.from_dict(
            {
                "task_id": "task-013",
                "task_type": "browser_action",
                "action_type": "browser.execute_click",
                "selector": "#btn",
                "approval_token": "secret-token",
            }
        )

        safe = schema.safe_dict()
        assert "approval_token" not in safe
        assert safe["task_id"] == "task-013"

    def test_final_approval_token_not_in_safe_dict(self):
        """final_approval_token removed from safe_dict"""
        schema = BrowserWebSocketTaskPayloadSchema.from_dict(
            {
                "task_id": "task-014",
                "task_type": "browser_action",
                "action_type": "browser.execute_click",
                "selector": "#btn",
                "final_approval_token": "final-token",
            }
        )

        safe = schema.safe_dict()
        assert "final_approval_token" not in safe


class TestMetadataConstraints:
    """Verify metadata field restrictions"""

    def test_metadata_forbidden_keys_rejected(self):
        """Forbidden keys in metadata rejected"""
        forbidden_keys_to_test = ["cookie", "session", "localStorage", "password"]

        for idx, forbidden_key in enumerate(forbidden_keys_to_test):
            data = {
                "task_id": f"task-015-{idx}",
                "task_type": "browser_action",
                "action_type": "browser.execute_click",
                "selector": "#btn",
                "metadata": {forbidden_key: "value"},
            }

            is_valid, _error = validate_payload_schema(data)
            assert is_valid is False, f"Forbidden key '{forbidden_key}' should be rejected but wasn't"


class TestResultSchema:
    """Validate output result schema"""

    def test_result_schema_accepts_safe_browser_result(self):
        """Result schema accepts safe browser result"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-016",
            status="executed",
            action="browser.execute_click",
            selector="#btn",
            executed=True,
            element_found=True,
            result="success",
        )

        is_safe, error = validate_result_schema(result)
        assert is_safe is True
        assert error is None

    def test_result_schema_requires_task_id(self):
        """Result schema requires task_id"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="",
            status="executed",
        )

        is_safe, _error = validate_result_schema(result)
        assert is_safe is False

    def test_result_text_preview_must_be_redacted(self):
        """text_preview must be '[REDACTED]'"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-017",
            status="executed",
            text_preview="actual typed text",
        )

        is_safe, error = validate_result_schema(result)
        assert is_safe is False
        assert "text_preview" in error.lower()

    def test_result_schema_rejects_approval_token(self):
        """Result cannot contain approval_token"""
        # Note: approval_token is not a field in BrowserWebSocketTaskResultSchema
        # This test verifies the schema enforces this
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-018",
            status="executed",
        )

        # Verify approval_token is not an attribute
        assert not hasattr(result, "approval_token")

    def test_result_schema_rejects_token_hash(self):
        """Result cannot contain token_hash"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-019",
            status="executed",
        )

        # Verify token_hash is not an attribute
        assert not hasattr(result, "token_hash")

    def test_result_schema_rejects_typed_text(self):
        """Result cannot contain raw typed text"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-020",
            status="executed",
        )

        # Verify typed_text is not an attribute
        assert not hasattr(result, "typed_text")


class TestResultSafeDictGeneration:
    """Verify result safe_dict() removes secrets"""

    def test_safe_dict_includes_allowed_fields(self):
        """safe_dict includes only allowed fields"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-021",
            status="executed",
            action="browser.execute_click",
            selector="#btn",
            executed=True,
            element_found=True,
        )

        safe = result.safe_dict()
        # Note: task_id is not in the allowed keys whitelist (reference is via task_id field in wrapper)
        assert "status" in safe
        assert "action" in safe
        assert safe["status"] == "executed"
        assert safe["action"] == "browser.execute_click"

    def test_safe_dict_excludes_forbidden_keys(self):
        """safe_dict excludes forbidden keys"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-022",
            status="executed",
        )

        safe = result.safe_dict()
        for forbidden_key in RESULT_DATA_FORBIDDEN_KEYS:
            assert forbidden_key not in safe

    def test_safe_dict_resets_text_preview(self):
        """safe_dict ensures text_preview is '[REDACTED]'"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-023",
            status="executed",
            text_preview="[REDACTED]",
        )

        safe = result.safe_dict()
        assert safe["text_preview"] == "[REDACTED]"


class TestStatusVocabulary:
    """Verify standard task status values"""

    def test_valid_status_values_recognized(self):
        """All VALID_TASK_STATUS values accepted"""
        for status in VALID_TASK_STATUS:
            result = BrowserWebSocketTaskResultSchema(
                task_id="task-024",
                status=status,
            )
            is_safe, _ = validate_result_schema(result)
            assert is_safe is True

    def test_executed_status_recognized(self):
        """'executed' status is valid"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-025",
            status="executed",
        )
        is_safe, _ = validate_result_schema(result)
        assert is_safe is True

    def test_blocked_status_recognized(self):
        """'blocked' status is valid"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-026",
            status="blocked",
        )
        is_safe, _ = validate_result_schema(result)
        assert is_safe is True

    def test_failed_status_recognized(self):
        """'failed' status is valid"""
        result = BrowserWebSocketTaskResultSchema(
            task_id="task-027",
            status="failed",
        )
        is_safe, _ = validate_result_schema(result)
        assert is_safe is True


class TestWhitelistConsistency:
    """Verify schema allowed fields match registry whitelist"""

    def test_result_allowed_keys_match_registry_whitelist(self):
        """Schema RESULT_DATA_ALLOWED_KEYS ⊆ registry whitelist"""
        registry_allowed = _reg._RESULT_DATA_ALLOWED_KEYS

        for key in RESULT_DATA_ALLOWED_KEYS:
            assert key in registry_allowed, f"Schema key '{key}' not in registry whitelist"

    def test_registry_whitelist_includes_browser_fields(self):
        """Registry whitelist includes all browser-specific result fields"""
        # Note: task_id is NOT in registry whitelist (result contains reference via task_id field in other contexts)
        browser_fields = {
            "status",
            "selector",
            "executed",
            "element_found",
            "risk_level",
            "final_approval_required",
            "result",
            "target_url_domain",
            "text_length",
            "text_preview",
            "error_message",
            "screenshot_ref",
            "action",
            "error_code",
            "screenshot_taken",
        }

        registry_allowed = _reg._RESULT_DATA_ALLOWED_KEYS
        for field in browser_fields:
            assert field in registry_allowed, f"Browser field '{field}' not in registry whitelist"

    def test_forbidden_keys_not_in_registry_whitelist(self):
        """RESULT_DATA_FORBIDDEN_KEYS not in registry whitelist"""
        registry_allowed = _reg._RESULT_DATA_ALLOWED_KEYS

        forbidden_in_whitelist = RESULT_DATA_FORBIDDEN_KEYS & registry_allowed
        assert len(forbidden_in_whitelist) == 0, f"Forbidden keys in whitelist: {forbidden_in_whitelist}"

    def test_sensitive_keys_blocked(self):
        """Sensitive keys are in registry _SENSITIVE_KEYS"""
        sensitive = _reg._SENSITIVE_KEYS

        sensitive_to_check = {"approval_token", "final_approval_token", "token_hash"}
        for key in sensitive_to_check:
            assert key in sensitive, f"Key '{key}' not in _SENSITIVE_KEYS"


class TestActionTypeRegistration:
    """Verify browser action types are registered"""

    def test_allowed_action_types_registered_in_action_risk(self):
        """All ALLOWED_ACTION_TYPES registered in ACTION_RISK"""
        action_risk = _reg.ACTION_RISK

        for action in ALLOWED_ACTION_TYPES:
            assert action in action_risk, f"Action '{action}' not in ACTION_RISK"

    def test_blocked_execute_submit_not_registered(self):
        """browser.execute_submit is NOT in ACTION_RISK"""
        action_risk = _reg.ACTION_RISK
        assert "browser.execute_submit" not in action_risk

    def test_allowed_actions_in_auto_execute_set(self):
        """All ALLOWED_ACTION_TYPES in AUTO_EXECUTE_VIA_AGENT"""
        auto_execute = _reg.AUTO_EXECUTE_VIA_AGENT

        for action in ALLOWED_ACTION_TYPES:
            assert action in auto_execute, f"Action '{action}' not in AUTO_EXECUTE_VIA_AGENT"


class TestPayloadFromDict:
    """Verify BrowserWebSocketTaskPayloadSchema.from_dict()"""

    def test_from_dict_creates_valid_schema(self):
        """from_dict creates valid schema instance"""
        data = {
            "task_id": "task-028",
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "approval_id": "appr-001",
        }

        schema = BrowserWebSocketTaskPayloadSchema.from_dict(data)
        assert schema.task_id == "task-028"
        assert schema.action_type == "browser.execute_click"

    def test_from_dict_raises_on_invalid_task_id(self):
        """from_dict raises ValueError on missing task_id"""
        data = {
            "task_type": "browser_action",
            "action_type": "browser.execute_click",
            "selector": "#btn",
        }

        with pytest.raises(ValueError, match="task_id"):
            BrowserWebSocketTaskPayloadSchema.from_dict(data)

    def test_from_dict_raises_on_blocked_action(self):
        """from_dict raises ValueError on blocked action"""
        data = {
            "task_id": "task-029",
            "task_type": "browser_action",
            "action_type": "browser.execute_submit",
            "selector": "#btn",
        }

        with pytest.raises(ValueError, match="blocked"):
            BrowserWebSocketTaskPayloadSchema.from_dict(data)


class TestResultFromTaskResult:
    """Verify BrowserWebSocketTaskResultSchema.from_task_result()"""

    def test_from_task_result_creates_valid_result(self):
        """from_task_result creates valid result schema"""
        result = BrowserWebSocketTaskResultSchema.from_task_result(
            task_id="task-030",
            status="executed",
            action="browser.execute_click",
            executed=True,
        )

        assert result.task_id == "task-030"
        assert result.status == "executed"
        assert result.executed is True

    def test_from_task_result_defaults_invalid_status(self):
        """from_task_result defaults invalid status to 'received'"""
        result = BrowserWebSocketTaskResultSchema.from_task_result(
            task_id="task-031",
            status="unknown_status",
        )

        assert result.status == "received"
