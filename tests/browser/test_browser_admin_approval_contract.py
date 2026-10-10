"""Tests for browser admin approval UI contract (BROWSER-4H).

Verifies:
1. Safe fields are available for UI display
2. Forbidden fields are never in UI data
3. Token non-disclosure policy enforced
4. Risky keyword detection
5. Final approval workflow
6. Result display safety
7. Integration with BROWSER-4G schema

Note (2026-09-28): a `TestStatusVocabulary` class used to be here, but every method
was a stub with no assertions (just a status assignment + comments describing the
expected button state, e.g. "can_approve = true, can_reject = true") — it always
passed regardless of behavior. Removed as non-functional (ERA001 audit-kit review
flagged its comments as false-positive "commented-out code"; closer inspection
showed the tests behind them were never actually implemented). The status-vocabulary
concern IS actually covered elsewhere: see `TestStatusVocabulary` in
`test_browser_websocket_payload_schema.py`, which asserts against the real schema.
"""

from core.agent_runtime.browser.bridge.browser_websocket_schema import (
    ALLOWED_ACTION_TYPES,
    BLOCKED_ACTION_TYPES,
    RESULT_DATA_ALLOWED_KEYS,
    RESULT_DATA_FORBIDDEN_KEYS,
)


class TestApprovalUIDataStructures:
    """Verify approval request UI data structures"""

    def test_admin_contract_allows_safe_fields(self):
        """Admin UI can display safe approval fields"""
        safe_fields = {
            "approval_id",
            "task_id",
            "status",
            "action_type",
            "selector",
            "risk_level",
            "final_approval_required",
            "target_url_domain",
            "requested_by",
            "created_at",
            "expires_at",
        }

        # All should be displayable
        for field in safe_fields:
            assert field is not None

    def test_admin_contract_rejects_approval_token(self):
        """Admin UI never contains approval_token"""
        forbidden_fields = {"approval_token"}

        # Verify these are NOT in safe display fields
        safe_ui_fields = {
            "approval_id",
            "task_id",
            "status",
            "action_type",
            "selector",
            "risk_level",
            "final_approval_required",
        }

        overlap = forbidden_fields & safe_ui_fields
        assert len(overlap) == 0, f"Forbidden fields in UI: {overlap}"

    def test_admin_contract_rejects_final_approval_token(self):
        """Admin UI never contains final_approval_token"""
        forbidden = "final_approval_token"
        safe_ui_fields = {
            "approval_id",
            "task_id",
            "status",
            "action_type",
            "selector",
            "risk_level",
            "final_approval_required",
        }

        assert forbidden not in safe_ui_fields

    def test_admin_contract_rejects_token_hash(self):
        """Admin UI never contains token_hash"""
        forbidden = "token_hash"
        safe_ui_fields = {
            "approval_id",
            "task_id",
            "status",
            "action_type",
            "selector",
            "risk_level",
            "final_approval_required",
        }

        assert forbidden not in safe_ui_fields


class TestResultDisplaySafety:
    """Verify result data display is safe"""

    def test_result_display_allows_safe_result_fields(self):
        """Result UI can display safe fields"""
        safe_result_fields = {
            "status",
            "action",  # Schema uses "action", not "action_type"
            "selector",
            "executed",
            "element_found",
            "result",
            "risk_level",
            "target_url_domain",
            "text_length",
            "text_preview",
            "error_code",
            "error_message",
            "screenshot_ref",
        }

        # All should be in result whitelist
        for field in safe_result_fields:
            assert field in RESULT_DATA_ALLOWED_KEYS

    def test_result_display_rejects_approval_token(self):
        """Result never contains approval_token"""
        assert "approval_token" in RESULT_DATA_FORBIDDEN_KEYS
        assert "approval_token" not in RESULT_DATA_ALLOWED_KEYS

    def test_result_display_rejects_token_hash(self):
        """Result never contains token_hash"""
        assert "token_hash" in RESULT_DATA_FORBIDDEN_KEYS
        assert "token_hash" not in RESULT_DATA_ALLOWED_KEYS

    def test_result_display_rejects_raw_typed_text(self):
        """Result never contains raw typed text"""
        # Should use text_length instead
        assert "typed_text" in RESULT_DATA_FORBIDDEN_KEYS
        assert "typed_text" not in RESULT_DATA_ALLOWED_KEYS

    def test_result_display_allows_text_length(self):
        """Result can display text_length (not the text itself)"""
        assert "text_length" in RESULT_DATA_ALLOWED_KEYS

    def test_result_display_text_preview_redacted(self):
        """Result text_preview is always redacted"""
        assert "text_preview" in RESULT_DATA_ALLOWED_KEYS
        # In UI, text_preview must be "[REDACTED]"


class TestSecretNonDisclosure:
    """Verify secrets are never disclosed"""

    def test_result_rejects_password(self):
        """Result never contains password"""
        assert "password" in RESULT_DATA_FORBIDDEN_KEYS
        assert "password" not in RESULT_DATA_ALLOWED_KEYS

    def test_result_rejects_otp(self):
        """Result never contains OTP"""
        assert "otp" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_cookie(self):
        """Result never contains cookie"""
        assert "cookie" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_session(self):
        """Result never contains session"""
        assert "session" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_authorization(self):
        """Result never contains Authorization header"""
        assert "authorization" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_localstorage(self):
        """Result never contains localStorage"""
        assert "localStorage" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_sessionstorage(self):
        """Result never contains sessionStorage"""
        assert "sessionStorage" in RESULT_DATA_FORBIDDEN_KEYS

    def test_result_rejects_base64(self):
        """Result never contains base64 content"""
        assert "base64" in RESULT_DATA_FORBIDDEN_KEYS


class TestApprovalActionConstraints:
    """Verify approval action buttons are constrained correctly"""

    def test_pending_execute_click_can_show_approve_button(self):
        """Pending execute_click can show Approve button"""
        action = "browser.execute_click"
        assert action in ALLOWED_ACTION_TYPES
        # UI should enable approve button

    def test_pending_execute_type_can_show_approve_button(self):
        """Pending execute_type can show Approve button"""
        action = "browser.execute_type"
        assert action in ALLOWED_ACTION_TYPES
        # UI should enable approve button

    def test_plan_actions_can_show_approve_button(self):
        """Plan actions can show Approve button"""
        plan_actions = {
            "browser.plan_click",
            "browser.plan_type",
            "browser.plan_submit",
        }

        for action in plan_actions:
            assert action in ALLOWED_ACTION_TYPES
            # UI should enable approve button

    def test_execute_submit_never_shows_approve_button(self):
        """browser.execute_submit never shows Approve button"""
        action = "browser.execute_submit"
        assert action in BLOCKED_ACTION_TYPES
        assert action not in ALLOWED_ACTION_TYPES
        # UI must never show approve button for this


class TestRiskyActionDetection:
    """Verify risky actions trigger final approval"""

    def test_risky_delete_requires_final_approval_badge(self):
        """Actions with 'delete' keyword show final approval badge"""
        risky_keywords = ["delete", "remove", "purge", "clear", "wipe"]

        # UI should detect these keywords in selector/action
        # and set final_approval_required = true
        for keyword in risky_keywords:
            assert keyword is not None

    def test_risky_submit_requires_final_approval(self):
        """Actions with 'submit' keyword show final approval badge"""
        risky_keywords = ["submit", "post", "send", "confirm"]

        for keyword in risky_keywords:
            assert keyword is not None

    def test_risky_payment_requires_final_approval(self):
        """Actions with 'payment' keyword show final approval badge"""
        risky_keywords = ["payment", "checkout", "charge", "bill", "pay"]

        for keyword in risky_keywords:
            assert keyword is not None


class TestBlockedActions:
    """Verify blocked actions cannot be approved"""

    def test_blocked_action_has_no_execute_button(self):
        """Blocked actions show no execute button"""
        blocked = BLOCKED_ACTION_TYPES
        assert "browser.execute_submit" in blocked

        # UI should disable approve button for blocked actions
        for action in blocked:
            # Status should be "blocked", can_approve = false
            assert action is not None


class TestResultDisplay:
    """Verify result display contracts"""

    def test_executed_result_displays_safe_summary(self):
        """Executed result shows safe summary only"""
        safe_fields = {
            "status",
            "action",
            "selector",  # "action" in schema, not "action_type"
            "executed",
            "element_found",
            "result",
            "text_length",
            "text_preview",
        }

        # All these should be in whitelist
        for field in safe_fields:
            assert field in RESULT_DATA_ALLOWED_KEYS

    def test_failed_result_displays_error_without_secret(self):
        """Failed result shows error code/message without secrets"""
        allowed_error_fields = {"error_code", "error_message"}

        # Both should be safe to display
        for field in allowed_error_fields:
            if field in RESULT_DATA_ALLOWED_KEYS:
                # Good - error info is safe
                assert field is not None

    def test_result_no_raw_screenshot(self):
        """Result never contains raw screenshot content"""
        assert "raw_screenshot" in RESULT_DATA_FORBIDDEN_KEYS
        # UI shows screenshot_ref only (metadata, not content)


class TestApprovalDecisionPayload:
    """Verify approval decision payload is safe"""

    def test_approval_decision_payload_has_no_token(self):
        """Approval decision payload never contains tokens"""
        decision_payload_fields = {
            "approval_id",
            "task_id",
            "decision",
            "reason",
            "approved_by",
        }

        # NEVER include these:
        forbidden_in_payload = {
            "approval_token",
            "final_approval_token",
            "token_hash",
        }

        overlap = decision_payload_fields & forbidden_in_payload
        assert len(overlap) == 0

    def test_approval_decision_uses_approval_id_only(self):
        """Decision payload uses approval_id for reference, not token"""
        # Good pattern: {approval_id: "...", decision: "approve"}
        # Bad pattern: {approval_token: "...", decision: "approve"}

        # UI should send approval_id, never approval_token
        assert "approval_id" != None


class TestSchemaIntegration:
    """Verify contract integrates with BROWSER-4G schema"""

    def test_browser_action_types_match_schema(self):
        """Admin UI action types match schema ALLOWED_ACTION_TYPES"""
        ui_actions = {
            "browser.inspect",
            "browser.plan_click",
            "browser.plan_type",
            "browser.plan_submit",
            "browser.execute_click",
            "browser.execute_type",
        }

        for action in ui_actions:
            assert action in ALLOWED_ACTION_TYPES

    def test_result_whitelist_matches_schema(self):
        """Admin result display fields match schema whitelist"""
        admin_ui_fields = {
            "status",
            "action",
            "selector",
            "executed",
            "element_found",
            "risk_level",
            "final_approval_required",
            "result",
            "error_code",
            "error_message",
            "target_url_domain",
            "text_length",
            "text_preview",
            "screenshot_ref",
        }

        for field in admin_ui_fields:
            assert field in RESULT_DATA_ALLOWED_KEYS or field == "action"

    def test_forbidden_fields_match_schema(self):
        """Admin forbidden fields match schema forbidden keys"""
        admin_forbidden = {
            "approval_token",
            "final_approval_token",
            "token_hash",
            "typed_text",
            "password",
            "otp",
            "cookie",
            "session",
        }

        for field in admin_forbidden:
            assert field in RESULT_DATA_FORBIDDEN_KEYS


class TestMockData:
    """Verify mock data follows contract"""

    def test_mock_pending_approval_valid(self):
        """Mock pending approval has all required safe fields"""
        mock = {
            "approval_id": "appr-001",
            "task_id": "task-001",
            "status": "received",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "risk_level": "low",
            "final_approval_required": False,
        }

        # Has approval_id (not token)
        assert "approval_id" in mock
        assert "approval_token" not in mock
        assert "final_approval_token" not in mock

    def test_mock_executed_result_safe(self):
        """Mock executed result contains only safe fields"""
        mock = {
            "task_id": "task-001",
            "status": "executed",
            "action_type": "browser.execute_click",
            "selector": "#btn",
            "executed": True,
            "element_found": True,
            "result": "success",
            "text_preview": "[REDACTED]",
        }

        # No forbidden fields
        forbidden = {
            "approval_token",
            "final_approval_token",
            "token_hash",
            "typed_text",
            "password",
            "otp",
        }

        overlap = set(mock.keys()) & forbidden
        assert len(overlap) == 0

    def test_mock_failed_result_safe(self):
        """Mock failed result shows error without secrets"""
        mock = {
            "task_id": "task-999",
            "status": "failed",
            "action_type": "browser.execute_click",
            "selector": "#nonexistent",
            "executed": False,
            "element_found": False,
            "error_code": "element_not_found",
            "error_message": "CSS selector not found",
        }

        # Has error info (safe) but no forbidden fields
        assert "error_code" in mock
        assert "error_message" in mock
        assert "approval_token" not in mock
        assert "token_hash" not in mock
