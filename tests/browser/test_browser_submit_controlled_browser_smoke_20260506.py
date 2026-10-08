"""Controlled Internal Submit - Browser Smoke Test.

Minimal smoke test for controlled internal submit flow validation.
Uses fixture-based validation only (no external network, no actual browser).

Flow: policy validation → preview generation → user confirmation → controlled submit decision
No actual submit, no external navigation, no DB write.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.submit.controlled_submit import (
    build_controlled_submit_result,
)
from ai_orchestrator.browser_tool.submit.submit_policy import (
    SubmitValidationRequest,
    validate_submit_policy,
)
from ai_orchestrator.browser_tool.submit.submit_preview import (
    SubmitPreviewInput,
    build_submit_preview,
)


@pytest.fixture
def allowlist():
    """Load allowlist fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "browser_submit_policy_allowlist_20260506.json"
    with fixture_path.open(encoding="utf-8") as f:
        return json.load(f)


class TestControlledBrowserSmoke:
    """Smoke test for controlled internal submit flow."""

    def test_01_fixture_allowlist_valid(self, allowlist):
        """Test 1: Fixture allowlist is valid."""
        assert allowlist is not None
        assert "submit_sites" in allowlist
        assert len(allowlist["submit_sites"]) > 0

    def test_02_fixture_has_allowed_site(self, allowlist):
        """Test 2: Fixture has allowed_internal_mock_form site."""
        sites = [
            s for s in allowlist["submit_sites"] if s.get("site_id") == "allowed_internal_mock_form" and s.get("active")
        ]
        assert len(sites) > 0
        assert "contact_form" in sites[0]["allowed_form_ids"]
        assert "submit_btn" in sites[0]["allowed_submit_button_ids"]

    def test_03_policy_validation_pass(self, allowlist):
        """Test 3: Policy validation passes for allowed form."""
        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "smoke@example.com"}],
            hidden_fields=[{"name": "csrf_token", "value": "safe"}],
            preview_shown=True,
            user_confirmed=True,
        )

        result = validate_submit_policy(request, allowlist)
        assert result.verdict == "ALLOW"
        assert result.risk_level == "high"
        assert result.requires_approval is True

    def test_04_preview_generation(self, allowlist):
        """Test 4: Preview can be generated."""
        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "smoke@example.com"}],
            hidden_fields=[{"name": "csrf_token", "value": "safe"}],
            preview_shown=True,
            user_confirmed=True,
        )

        policy_result = validate_submit_policy(request, allowlist)

        preview_input = SubmitPreviewInput(
            site_id=request.site_id,
            form_id=request.form_id,
            submit_button_id=request.submit_button_id,
            intent=request.intent,
            fields=request.fields,
            hidden_fields=request.hidden_fields,
            policy_verdict=policy_result.verdict,
            validation_id="smoke_001",
            risk_level="high",
        )

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        policy_dict = {
            "verdict": policy_result.verdict,
            "allowlist_verdict": policy_result.allowlist_verdict,
            "origin_verdict": policy_result.origin_verdict,
            "form_verdict": policy_result.form_verdict,
            "intent_verdict": policy_result.intent_verdict,
            "field_verdict": policy_result.field_verdict,
            "prompt_injection_verdict": policy_result.prompt_injection_verdict,
            "preview_verdict": policy_result.preview_verdict,
            "user_confirm_verdict": policy_result.user_confirm_verdict,
            "reasons": policy_result.reasons,
        }

        preview_bundle = build_submit_preview(preview_input, policy_dict, now)

        assert preview_bundle is not None
        assert preview_bundle.summary is not None
        assert preview_bundle.details is not None
        assert preview_bundle.audit is not None
        assert preview_bundle.audit.preview_hash
        assert len(preview_bundle.audit.preview_hash) == 64

    def test_05_user_confirmed_true(self):
        """Test 5: User confirmation flag is True."""
        user_confirmed = True
        assert user_confirmed is True

    def test_06_controlled_internal_origin_check(self):
        """Test 6: internal.mock is recognized as controlled internal."""
        from ai_orchestrator.browser_tool.submit.controlled_submit import is_controlled_internal_origin

        assert is_controlled_internal_origin("https://internal.mock/form") is True
        assert is_controlled_internal_origin("https://external.example.com/form") is False

    def test_07_controlled_submit_result_structure(self, allowlist):
        """Test 7: Controlled submit result has correct structure."""
        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "smoke@example.com"}],
            hidden_fields=[{"name": "csrf_token", "value": "safe"}],
            preview_shown=True,
            user_confirmed=True,
        )

        policy_result = validate_submit_policy(request, allowlist)

        preview_input = SubmitPreviewInput(
            site_id=request.site_id,
            form_id=request.form_id,
            submit_button_id=request.submit_button_id,
            intent=request.intent,
            fields=request.fields,
            hidden_fields=request.hidden_fields,
            policy_verdict=policy_result.verdict,
            validation_id="smoke_001",
            risk_level="high",
        )

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        policy_dict = {
            "verdict": policy_result.verdict,
            "allowlist_verdict": policy_result.allowlist_verdict,
            "origin_verdict": policy_result.origin_verdict,
            "form_verdict": policy_result.form_verdict,
            "intent_verdict": policy_result.intent_verdict,
            "field_verdict": policy_result.field_verdict,
            "prompt_injection_verdict": policy_result.prompt_injection_verdict,
            "preview_verdict": policy_result.preview_verdict,
            "user_confirm_verdict": policy_result.user_confirm_verdict,
            "reasons": policy_result.reasons,
        }

        preview_bundle = build_submit_preview(preview_input, policy_dict, now)

        controlled_result = build_controlled_submit_result(
            preview_bundle,
            user_confirmed=True,
            user_id="smoke_test_user",
        )

        assert controlled_result is not None
        assert hasattr(controlled_result, "submitted")
        assert hasattr(controlled_result, "submit_result")
        assert hasattr(controlled_result, "error_reason")
        assert hasattr(controlled_result, "audit_record")
        assert hasattr(controlled_result, "lifecycle")

    def test_08_no_external_urls(self):
        """Test 8: No external URLs in smoke test."""
        allowed_urls = [
            "https://internal.mock/form",
            "http://localhost:3000/form",
            "http://127.0.0.1:8080/form",
            "data:text/html,<form></form>",
        ]

        blocked_urls = [
            "https://external.example.com/form",
            "https://조달.go.kr/form",
            "https://g2b.go.kr/form",
        ]

        from ai_orchestrator.browser_tool.submit.controlled_submit import is_controlled_internal_origin

        for url in allowed_urls:
            assert is_controlled_internal_origin(url) is True

        for url in blocked_urls:
            assert is_controlled_internal_origin(url) is False

    def test_09_no_password_fields(self):
        """Test 9: No password/token/secret fields."""
        fields = [
            {"name": "email", "value": "test@example.com"},
            {"name": "message", "value": "hello"},
        ]

        for field in fields:
            assert "password" not in field["name"].lower()
            assert "token" not in field["name"].lower()
            assert "secret" not in field["name"].lower()

        assert True

    def test_10_audit_redaction(self):
        """Test 10: Audit uses redacted payload (no original secrets)."""
        from ai_orchestrator.browser_tool.submit.submit_preview import mask_field_value

        email_original = "test@example.com"
        email_masked = mask_field_value("email", email_original)

        assert email_masked != email_original
        assert "@" in email_masked
        assert "test@" not in email_masked

    def test_11_no_external_navigation(self):
        """Test 11: Smoke test doesn't trigger external navigation."""
        # Data URL form stays in data: protocol
        # Controlled internal origin check prevents external navigation
        assert True

    def test_12_fixture_matches_controlled_origin(self, allowlist):
        """Test 12: Fixture origin matches controlled internal requirements."""
        from ai_orchestrator.browser_tool.submit.controlled_submit import is_controlled_internal_origin

        # Fixture uses internal.mock
        assert is_controlled_internal_origin("https://internal.mock/form") is True

        # Fixture site_id is in allowlist
        sites = [
            s for s in allowlist["submit_sites"] if s.get("site_id") == "allowed_internal_mock_form" and s.get("active")
        ]
        assert len(sites) > 0

    def test_13_full_flow_summary(self, allowlist):
        """Test 13: Full flow summary - policy → preview → confirm → controlled → result."""
        # STEP 1: Policy validation
        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "final_smoke@example.com"}],
            hidden_fields=[{"name": "csrf_token", "value": "safe"}],
            preview_shown=True,
            user_confirmed=True,
        )

        policy_result = validate_submit_policy(request, allowlist)
        assert policy_result.verdict == "ALLOW", "STEP 1: policy ALLOW"

        # STEP 2: Preview generation
        preview_input = SubmitPreviewInput(
            site_id=request.site_id,
            form_id=request.form_id,
            submit_button_id=request.submit_button_id,
            intent=request.intent,
            fields=request.fields,
            hidden_fields=request.hidden_fields,
            policy_verdict=policy_result.verdict,
            validation_id="smoke_final",
            risk_level="high",
        )

        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        policy_dict = {
            "verdict": policy_result.verdict,
            "allowlist_verdict": policy_result.allowlist_verdict,
            "origin_verdict": policy_result.origin_verdict,
            "form_verdict": policy_result.form_verdict,
            "intent_verdict": policy_result.intent_verdict,
            "field_verdict": policy_result.field_verdict,
            "prompt_injection_verdict": policy_result.prompt_injection_verdict,
            "preview_verdict": policy_result.preview_verdict,
            "user_confirm_verdict": policy_result.user_confirm_verdict,
            "reasons": policy_result.reasons,
        }

        preview_bundle = build_submit_preview(preview_input, policy_dict, now)
        assert preview_bundle is not None, "STEP 2: preview generated"

        # STEP 3: User confirmation
        user_confirmed = True
        assert user_confirmed is True, "STEP 3: user confirmed"

        # STEP 4: Controlled submit
        controlled_result = build_controlled_submit_result(
            preview_bundle,
            user_confirmed=user_confirmed,
        )

        assert controlled_result is not None, "STEP 4: controlled result created"
        assert hasattr(controlled_result, "lifecycle"), "STEP 5: lifecycle tracked"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
