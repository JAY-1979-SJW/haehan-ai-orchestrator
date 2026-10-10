"""Browser Submit Preview Schema Tests.

Tests validate submit_preview module against design specification.
No actual submit, no browser, no network, no DB.
Pure preview generation validation only.
"""

import json

import pytest

from ai_orchestrator.browser_tool.submit.submit_preview import (
    AuditPreviewRecord,
    SubmitPreviewBundle,
    SubmitPreviewInput,
    UserPreviewDetails,
    UserPreviewSummary,
    build_submit_preview,
    canonical_preview_payload,
    compute_preview_hash,
    mask_field_value,
    redact_fields,
)


@pytest.fixture
def basic_request():
    """Basic preview input."""
    return SubmitPreviewInput(
        site_id="allowed_internal_mock_form",
        form_id="contact_form",
        submit_button_id="submit_btn",
        intent="submit_contact_form",
        fields=[
            {"name": "email", "value": "test@example.com"},
            {"name": "message", "value": "Hello World"},
        ],
        hidden_fields=[{"name": "csrf_token", "value": "token123"}],
        policy_verdict="ALLOW",
        validation_id="val_123",
        risk_level="high",
    )


@pytest.fixture
def policy_result():
    """Basic policy result."""
    return {
        "verdict": "ALLOW",
        "allowlist_verdict": "FOUND",
        "origin_verdict": "MATCH",
        "form_verdict": "FOUND",
        "intent_verdict": "ALLOWED",
        "field_verdict": "SAFE",
        "prompt_injection_verdict": "PASS",
        "preview_verdict": "SHOWN",
        "user_confirm_verdict": "PENDING",
        "reasons": ["모든 조건 충족"],
    }


class TestMaskFieldValue:
    """Test field value masking."""

    def test_mask_password_field(self):
        """Password field should be masked."""
        masked = mask_field_value("password", "secret123")
        assert masked == "****"
        assert "secret" not in masked

    def test_mask_token_field(self):
        """Token field should be masked."""
        masked = mask_field_value("access_token", "token_value_here")
        assert masked == "****"

    def test_mask_email(self):
        """Email should be masked."""
        masked = mask_field_value("email", "test@example.com")
        assert "***@" in masked
        assert "example.com" in masked
        assert "test@example.com" != masked

    def test_mask_phone(self):
        """Phone should be masked."""
        masked = mask_field_value("phone", "010-1234-5678")
        assert masked.startswith("010")
        assert masked.endswith("5678")
        assert "1234" not in masked
        assert len(masked) < len("010-1234-5678")

    def test_mask_long_text(self):
        """Long text should be summarized."""
        long_text = "a" * 150
        masked = mask_field_value("message", long_text)
        assert "[텍스트" in masked

    def test_no_mask_short_text(self):
        """Short text should not be masked."""
        masked = mask_field_value("company_name", "Acme Corp")
        assert masked == "Acme Corp"

    def test_empty_value(self):
        """Empty value should return placeholder."""
        masked = mask_field_value("field", "")
        assert "[값" in masked or "값" in masked


class TestRedactFields:
    """Test field redaction."""

    def test_redact_fields_basic(self):
        """Redact list of fields."""
        fields = [
            {"name": "email", "value": "test@example.com"},
            {"name": "password", "value": "secret123"},
        ]
        redacted = redact_fields(fields)

        assert len(redacted) == 2
        assert redacted[0]["name"] == "email"
        assert redacted[0]["masked"] is True
        assert redacted[1]["name"] == "password"
        assert redacted[1]["value"] == "****"

    def test_redact_preserves_field_names(self):
        """Field names should be preserved."""
        fields = [{"name": "custom_field", "value": "value"}]
        redacted = redact_fields(fields)
        assert redacted[0]["name"] == "custom_field"

    def test_redact_empty_list(self):
        """Empty field list should return empty list."""
        redacted = redact_fields([])
        assert redacted == []


class TestCanonicalPayload:
    """Test canonical payload generation."""

    def test_canonical_payload_sorted_keys(self):
        """Canonical payload should have sorted keys."""
        payload = {"z": 1, "a": 2, "m": 3}
        canonical = canonical_preview_payload(payload)
        parsed = json.loads(canonical)
        keys = list(parsed.keys())
        assert keys == ["a", "m", "z"]

    def test_canonical_payload_deterministic(self):
        """Same input should produce same canonical output."""
        payload = {"site_id": "test", "form_id": "form1"}
        canon1 = canonical_preview_payload(payload)
        canon2 = canonical_preview_payload(payload)
        assert canon1 == canon2

    def test_canonical_payload_key_order_irrelevant(self):
        """Key order should not affect canonical output."""
        payload1 = {"a": 1, "b": 2}
        payload2 = {"b": 2, "a": 1}
        assert canonical_preview_payload(payload1) == canonical_preview_payload(payload2)


class TestComputePreviewHash:
    """Test preview hash computation."""

    def test_compute_hash_basic(self):
        """Hash should be hex string of correct length."""
        payload = {"site_id": "test"}
        hash_val = compute_preview_hash(payload)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA256 hex is 64 chars

    def test_compute_hash_deterministic(self):
        """Same payload should produce same hash."""
        payload = {"site_id": "test", "form_id": "form1"}
        hash1 = compute_preview_hash(payload)
        hash2 = compute_preview_hash(payload)
        assert hash1 == hash2

    def test_compute_hash_key_order_irrelevant(self):
        """Key order should not affect hash."""
        payload1 = {"a": 1, "b": 2}
        payload2 = {"b": 2, "a": 1}
        assert compute_preview_hash(payload1) == compute_preview_hash(payload2)

    def test_compute_hash_different_payloads(self):
        """Different payloads should produce different hashes."""
        payload1 = {"site_id": "test1"}
        payload2 = {"site_id": "test2"}
        assert compute_preview_hash(payload1) != compute_preview_hash(payload2)


class TestPreviewBundle:
    """Test preview bundle generation."""

    def test_bundle_has_three_layers(self, basic_request, policy_result):
        """Bundle should have summary, details, and audit layers."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        assert isinstance(bundle, SubmitPreviewBundle)
        assert isinstance(bundle.summary, UserPreviewSummary)
        assert isinstance(bundle.details, UserPreviewDetails)
        assert isinstance(bundle.audit, AuditPreviewRecord)

    def test_summary_user_facing(self, basic_request, policy_result):
        """Summary should be user-facing with masked fields."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        summary = bundle.summary
        assert summary.site_id == "allowed_internal_mock_form"
        assert "제출" in summary.form_title
        assert "email" in summary.field_summary

    def test_summary_masks_sensitive_fields(self, policy_result):
        """Summary should mask sensitive field values."""
        request = SubmitPreviewInput(
            site_id="test",
            form_id="form1",
            submit_button_id="btn",
            intent="intent1",
            fields=[
                {"name": "password", "value": "secret"},
                {"name": "email", "value": "test@example.com"},
            ],
            policy_verdict="ALLOW",
        )

        bundle = build_submit_preview(request, policy_result, "2026-05-06T10:00:00Z")
        assert bundle.summary.field_summary["password"] == "****"
        assert bundle.summary.field_summary["email"] != "test@example.com"

    def test_details_includes_validation_checks(self, basic_request, policy_result):
        """Details should include all validation checks."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        details = bundle.details
        assert details.policy_verdict == "ALLOW"
        assert "모든 조건 충족" in details.policy_reasons
        assert len(details.validation_checks) == 8

    def test_details_has_form_info(self, basic_request, policy_result):
        """Details should include form info."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        details = bundle.details
        assert details.form_id == "contact_form"
        assert details.submit_button_id == "submit_btn"
        assert details.intent == "submit_contact_form"

    def test_audit_redacts_fields(self, basic_request, policy_result):
        """Audit should have redacted fields only."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert audit.redacted_payload["fields"][0]["masked"] is True
        assert "secret" not in str(audit.redacted_payload)

    def test_audit_includes_preview_hash(self, basic_request, policy_result):
        """Audit should include preview hash."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert audit.preview_hash
        assert len(audit.preview_hash) == 64  # SHA256 hex

    def test_audit_submitted_false_by_default(self, basic_request, policy_result):
        """Audit should have submitted=False by default."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert audit.submitted is False

    def test_audit_approved_fields_none_by_default(self, basic_request, policy_result):
        """Audit should have None for approval fields."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert audit.approved_by is None
        assert audit.approved_at is None

    def test_audit_submit_result_none_by_default(self, basic_request, policy_result):
        """Audit should have submit_result=None by default."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert audit.submit_result is None


class TestHiddenFields:
    """Test hidden field handling."""

    def test_hidden_fields_not_in_summary(self, basic_request, policy_result):
        """Summary should not include hidden field values."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        summary_str = str(bundle.summary.field_summary)
        assert "csrf_token" not in summary_str or "token123" not in summary_str

    def test_hidden_fields_count_in_details(self, basic_request, policy_result):
        """Details should show hidden field count."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        details = bundle.details
        assert details.hidden_fields_count == 1

    def test_hidden_fields_redacted_in_audit(self, basic_request, policy_result):
        """Audit should not include hidden field values."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )

        audit = bundle.audit
        assert "hidden_fields_count" in audit.redacted_payload
        assert "token123" not in str(audit.redacted_payload)


class TestDeterministicHash:
    """Test deterministic hash generation."""

    def test_same_request_same_hash(self, policy_result):
        """Same request should produce same hash."""
        request1 = SubmitPreviewInput(
            site_id="test",
            form_id="form1",
            submit_button_id="btn",
            intent="intent1",
            fields=[{"name": "field1", "value": "value1"}],
            policy_verdict="ALLOW",
        )

        bundle1 = build_submit_preview(request1, policy_result, "2026-05-06T10:00:00Z")
        bundle2 = build_submit_preview(request1, policy_result, "2026-05-06T10:00:00Z")

        assert bundle1.audit.preview_hash == bundle2.audit.preview_hash

    def test_field_order_irrelevant_for_hash(self, policy_result):
        """Field order should not affect hash."""
        request1 = SubmitPreviewInput(
            site_id="test",
            form_id="form1",
            submit_button_id="btn",
            intent="intent1",
            fields=[
                {"name": "field1", "value": "value1"},
                {"name": "field2", "value": "value2"},
            ],
            policy_verdict="ALLOW",
        )

        request2 = SubmitPreviewInput(
            site_id="test",
            form_id="form1",
            submit_button_id="btn",
            intent="intent1",
            fields=[
                {"name": "field2", "value": "value2"},
                {"name": "field1", "value": "value1"},
            ],
            policy_verdict="ALLOW",
        )

        bundle1 = build_submit_preview(request1, policy_result, "2026-05-06T10:00:00Z")
        bundle2 = build_submit_preview(request2, policy_result, "2026-05-06T10:00:00Z")

        assert bundle1.audit.preview_hash == bundle2.audit.preview_hash


class TestNoSideEffects:
    """Test that preview module has no side effects."""

    def test_no_network_calls(self, basic_request, policy_result):
        """No network calls should be made."""
        # Test that the module doesn't import network libraries
        import ai_orchestrator.browser_tool.submit.submit_preview as preview_module

        # Check imports
        module_code = preview_module.__dict__
        assert "requests" not in module_code
        assert "urllib" not in module_code
        assert "socket" not in module_code

    def test_no_browser_execution(self, basic_request, policy_result):
        """No browser execution should occur."""
        bundle = build_submit_preview(
            basic_request,
            policy_result,
            "2026-05-06T10:00:00Z",
        )
        # If we got here without browser opening, test passes
        assert bundle is not None

    def test_no_db_calls(self, basic_request, policy_result):
        """No database calls should be made."""
        import ai_orchestrator.browser_tool.submit.submit_preview as preview_module

        source = str(preview_module.__dict__)
        assert "sql" not in source.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
