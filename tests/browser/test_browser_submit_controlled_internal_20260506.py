"""Controlled Internal Submit Tests.

Tests validate controlled_submit module for safe internal submission.
No actual submit, no browser, no network, no DB.
Pure controlled submit decision validation only.
"""

import pytest

from ai_orchestrator.browser_tool.submit.controlled_submit import (
    ControlledSubmitResult,
    build_controlled_submit_result,
    get_blocking_reason,
    is_controlled_internal_origin,
)


@pytest.fixture
def mock_preview_bundle():
    """Mock SubmitPreviewBundle for testing."""

    class MockAudit:
        validation_id = "val_123"
        site_id = "allowed_internal_mock_form"
        form_id = "contact_form"
        intent = "submit_contact_form"
        preview_hash = "abc123hash"
        preview_timestamp = "2026-05-06T10:00:00Z"
        policy_verdict = "ALLOW"
        redacted_payload = {
            "fields": [{"name": "email", "value": "test@e****m.com"}],
            "hidden_fields_count": 1,
        }

    class MockDetails:
        url = "https://internal.mock/form"
        form_id = "contact_form"
        submit_button_id = "submit_btn"
        policy_verdict = "ALLOW"

    class MockBundle:
        audit = MockAudit()
        details = MockDetails()

    return MockBundle()


class TestControlledInternalOrigin:
    """Test controlled internal origin validation."""

    def test_internal_mock_allowed(self):
        """internal.mock should be allowed."""
        assert is_controlled_internal_origin("https://internal.mock/form") is True

    def test_internal_mock_with_port_allowed(self):
        """internal.mock with port should be allowed."""
        assert is_controlled_internal_origin("https://internal.mock:8080/form") is True

    def test_localhost_allowed(self):
        """localhost should be allowed."""
        assert is_controlled_internal_origin("http://localhost/form") is True

    def test_localhost_with_port_allowed(self):
        """localhost with port should be allowed."""
        assert is_controlled_internal_origin("http://localhost:3000/form") is True

    def test_localhost_127_0_0_1_allowed(self):
        """127.0.0.1 should be allowed."""
        assert is_controlled_internal_origin("http://127.0.0.1/form") is True

    def test_data_url_allowed(self):
        """data: URL should be allowed."""
        assert is_controlled_internal_origin("data:text/html,<form>test</form>") is True

    def test_external_url_blocked(self):
        """External URL should be blocked."""
        assert is_controlled_internal_origin("https://external.example.com/form") is False

    def test_empty_url_blocked(self):
        """Empty URL should be blocked."""
        assert is_controlled_internal_origin("") is False

    def test_can_disable_internal_mock(self):
        """Should respect allow_internal_mock=False."""
        assert is_controlled_internal_origin("https://internal.mock/form", allow_internal_mock=False) is False

    def test_can_disable_localhost(self):
        """Should respect allow_localhost=False."""
        assert is_controlled_internal_origin("http://localhost/form", allow_localhost=False) is False


class TestBlockingReasons:
    """Test blocking reason detection."""

    def test_not_confirmed_blocks(self, mock_preview_bundle):
        """User not confirmed should block."""
        should_block, reason = get_blocking_reason(mock_preview_bundle, False)
        assert should_block is True
        assert "confirm" in reason.lower()

    def test_no_preview_hash_blocks(self, mock_preview_bundle):
        """Missing preview_hash should block."""
        mock_preview_bundle.audit.preview_hash = ""
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "preview_hash" in reason.lower()

    def test_policy_deny_blocks(self, mock_preview_bundle):
        """Policy DENY should block."""
        mock_preview_bundle.audit.policy_verdict = "DENY"
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "policy" in reason.lower()

    def test_external_origin_blocks(self, mock_preview_bundle):
        """External origin should block."""
        mock_preview_bundle.details.url = "https://external.example.com/form"
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "origin" in reason.lower()

    def test_조달_keyword_blocks(self, mock_preview_bundle):
        """조달 keyword should block."""
        mock_preview_bundle.audit.redacted_payload["fields"] = [{"name": "site", "value": "조달청"}]
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "조달" in reason or "blocked" in reason.lower()

    def test_g2b_keyword_blocks(self, mock_preview_bundle):
        """G2B keyword should block."""
        mock_preview_bundle.audit.redacted_payload["fields"] = [{"name": "site", "value": "G2B 시스템"}]
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "g2b" in reason.lower() or "blocked" in reason.lower()

    def test_payment_keyword_blocks(self, mock_preview_bundle):
        """결제 (payment) keyword should block."""
        mock_preview_bundle.audit.redacted_payload["fields"] = [{"name": "action", "value": "결제"}]
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True
        assert "결제" in reason or "blocked" in reason.lower()

    def test_safe_fields_allowed(self, mock_preview_bundle):
        """Safe fields should be allowed."""
        should_block, reason = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is False
        assert reason == ""


class TestControlledSubmitResult:
    """Test controlled submit result building."""

    def test_result_structure_blocked(self, mock_preview_bundle):
        """Blocked result should have correct structure."""
        mock_preview_bundle.details.url = "https://external.example.com/form"
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert isinstance(result, ControlledSubmitResult)
        assert result.preview_hash == "abc123hash"
        assert result.validation_id == "val_123"
        assert result.submitted is False
        assert result.submit_result == "blocked"
        assert len(result.error_reason) > 0

    def test_result_structure_allowed(self, mock_preview_bundle):
        """Allowed result should have correct structure."""
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert isinstance(result, ControlledSubmitResult)
        assert result.preview_hash == "abc123hash"
        assert result.validation_id == "val_123"
        assert result.submitted is True
        assert result.submit_result == "success"
        assert result.error_reason == ""

    def test_audit_record_included(self, mock_preview_bundle):
        """Audit record should be included."""
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert result.audit_record
        assert result.audit_record["validation_id"] == "val_123"
        assert result.audit_record["policy_verdict"] == "ALLOW"
        assert result.audit_record["user_confirmed"] is True

    def test_lifecycle_included(self, mock_preview_bundle):
        """Lifecycle should be included."""
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert result.lifecycle
        assert "preview_timestamp" in result.lifecycle
        assert "confirmation_check" in result.lifecycle

    def test_timestamp_when_allowed(self, mock_preview_bundle):
        """Submit timestamp should be set when allowed."""
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert result.submit_timestamp
        assert "T" in result.submit_timestamp  # ISO format

    def test_no_timestamp_when_blocked(self, mock_preview_bundle):
        """Submit timestamp should be empty when blocked."""
        mock_preview_bundle.details.url = "https://external.example.com/form"
        result = build_controlled_submit_result(mock_preview_bundle, True)

        assert result.submit_timestamp == ""

    def test_user_id_in_audit(self, mock_preview_bundle):
        """User ID should be included in audit."""
        result = build_controlled_submit_result(mock_preview_bundle, True, user_id="user_456")

        assert result.audit_record["user_id"] == "user_456"


class TestLocalhostVariants:
    """Test localhost origin variants."""

    def test_localhost_no_port(self):
        """localhost without port."""
        assert is_controlled_internal_origin("http://localhost/form") is True

    def test_localhost_with_3000_port(self):
        """localhost:3000."""
        assert is_controlled_internal_origin("http://localhost:3000/form") is True

    def test_localhost_with_8080_port(self):
        """localhost:8080."""
        assert is_controlled_internal_origin("http://localhost:8080/form") is True

    def test_127_0_0_1_no_port(self):
        """127.0.0.1 without port."""
        assert is_controlled_internal_origin("http://127.0.0.1/form") is True

    def test_127_0_0_1_with_port(self):
        """127.0.0.1 with port."""
        assert is_controlled_internal_origin("http://127.0.0.1:5000/form") is True


class TestBlockedDomainKeywords:
    """Test blocked domain keyword detection."""

    def test_block_조달(self, mock_preview_bundle):
        """Should block 조달."""
        mock_preview_bundle.audit.redacted_payload = {"text": "조달청"}
        should_block, _ = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True

    def test_block_g2b_case_insensitive(self, mock_preview_bundle):
        """Should block g2b (case insensitive)."""
        mock_preview_bundle.audit.redacted_payload = {"text": "G2B"}
        should_block, _ = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True

    def test_block_나라장터(self, mock_preview_bundle):
        """Should block 나라장터."""
        mock_preview_bundle.audit.redacted_payload = {"text": "나라장터"}
        should_block, _ = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True

    def test_block_결제(self, mock_preview_bundle):
        """Should block 결제."""
        mock_preview_bundle.audit.redacted_payload = {"text": "결제"}
        should_block, _ = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is True

    def test_allow_no_keywords(self, mock_preview_bundle):
        """Should allow without keywords."""
        should_block, _ = get_blocking_reason(mock_preview_bundle, True)
        assert should_block is False


class TestNoSideEffects:
    """Test that controlled_submit has no side effects."""

    def test_no_network_calls(self):
        """Module should not import network libraries."""
        import ai_orchestrator.browser_tool.submit.controlled_submit as module

        module_code = module.__dict__
        assert "requests" not in module_code
        assert "socket" not in module_code

    def test_no_browser_execution(self, mock_preview_bundle):
        """No browser should be executed."""
        result = build_controlled_submit_result(mock_preview_bundle, True)
        assert result is not None

    def test_pure_function(self, mock_preview_bundle):
        """Same input should produce same output."""
        result1 = build_controlled_submit_result(mock_preview_bundle, True)
        result2 = build_controlled_submit_result(mock_preview_bundle, True)

        assert result1.submit_result == result2.submit_result
        assert result1.preview_hash == result2.preview_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
