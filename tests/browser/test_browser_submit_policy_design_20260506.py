"""Browser Submit Policy Design Validation Tests.

This module tests the submit policy design (BROWSER_SUBMIT_POLICY_DESIGN_1).
Tests validate:
  - Fixture JSON syntax and structure
  - Required keys presence
  - Policy verdicts (allow vs deny)
  - Field validation rules
  - Prompt injection detection patterns
  - External site domain filtering

Note: This stage contains DESIGN VALIDATION ONLY.
No actual submit implementation, browser execution, network calls, or DB operations.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_submit_policy_allowlist_20260506.json"


class TestBrowserSubmitPolicyFixtureStructure:
    """Validate fixture JSON structure and required fields."""

    def test_fixture_file_exists(self):
        """Fixture file must exist."""
        assert FIXTURE_PATH.exists(), f"Fixture file not found: {FIXTURE_PATH}"

    def test_fixture_json_syntax(self):
        """Fixture JSON must be valid."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict), "Fixture root must be dict"

    def test_fixture_required_top_level_keys(self):
        """Fixture must have required top-level keys."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        required_keys = {"version", "description", "created_at", "submit_sites"}
        assert required_keys.issubset(data.keys()), f"Missing keys: {required_keys - set(data.keys())}"

    def test_fixture_submit_sites_is_list(self):
        """submit_sites must be a list."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data["submit_sites"], list), "submit_sites must be list"
        assert len(data["submit_sites"]) > 0, "submit_sites must not be empty"

    def test_each_site_has_required_fields(self):
        """Each site entry must have all required fields."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        required_site_fields = {
            "site_id",
            "site_name",
            "description",
            "allowed_origins",
            "allowed_form_ids",
            "allowed_submit_button_ids",
            "allowed_intents",
            "denied_fields",
            "requires_preview",
            "requires_user_confirm",
            "requires_human_approval",
            "audit_level",
            "max_risk_level",
            "active",
        }

        for site in data["submit_sites"]:
            missing = required_site_fields - set(site.keys())
            assert not missing, f"Site {site.get('site_id')} missing fields: {missing}"

    def test_site_id_unique(self):
        """Each site_id must be unique."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site_ids = [site["site_id"] for site in data["submit_sites"]]
        assert len(site_ids) == len(set(site_ids)), "Duplicate site_id found"


class TestBrowserSubmitPolicyAllowedCases:
    """Validate that allowed cases have correct policy settings."""

    def test_allowed_internal_mock_form_has_preview_required(self):
        """allowed_internal_mock_form must require preview."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "allowed_internal_mock_form"),
            None,
        )
        assert site is not None, "allowed_internal_mock_form not found"
        assert site["requires_preview"] is True, "Must require preview"

    def test_allowed_internal_mock_form_has_user_confirm_required(self):
        """allowed_internal_mock_form must require user confirmation."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "allowed_internal_mock_form"),
            None,
        )
        assert site is not None, "allowed_internal_mock_form not found"
        assert site["requires_user_confirm"] is True, "Must require user confirmation"

    def test_allowed_internal_mock_form_is_active(self):
        """allowed_internal_mock_form must be active."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "allowed_internal_mock_form"),
            None,
        )
        assert site is not None, "allowed_internal_mock_form not found"
        assert site["active"] is True, "Must be active"

    def test_allowed_internal_mock_form_has_audit_level(self):
        """allowed_internal_mock_form must have audit_level set."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "allowed_internal_mock_form"),
            None,
        )
        assert site is not None, "allowed_internal_mock_form not found"
        assert site["audit_level"] in ["basic", "detailed", "verbose"], "Invalid audit_level"


class TestBrowserSubmitPolicyDeniedCases:
    """Validate that denied cases have correct policy settings."""

    def test_denied_unknown_origin_inactive_and_has_reason(self):
        """denied_unknown_origin must be inactive and have reason."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_unknown_origin"),
            None,
        )
        assert site is not None, "denied_unknown_origin not found"
        assert site["active"] is False, "Must be inactive"
        assert "reason_denied" in site or "test_case" in site, "Must have reason for denial"

    def test_denied_login_form_has_password_in_denied_fields(self):
        """denied_login_form_with_password must have password in denied_fields."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_login_form_with_password"),
            None,
        )
        assert site is not None, "denied_login_form_with_password not found"
        assert "password" in site["denied_fields"], "password must be in denied_fields"

    def test_denied_payment_form_not_in_allowed_intents(self):
        """denied_payment_form must not have payment intent in allowed_intents."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_payment_form"),
            None,
        )
        assert site is not None, "denied_payment_form not found"
        # Allowed intents should be empty or not contain payment intents
        assert len(site["allowed_intents"]) == 0, "Payment form should have no allowed intents"

    def test_denied_delete_action_not_in_allowed_intents(self):
        """denied_delete_action must not have delete intent in allowed_intents."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_delete_action"),
            None,
        )
        assert site is not None, "denied_delete_action not found"
        assert len(site["allowed_intents"]) == 0, "Delete form should have no allowed intents"

    def test_denied_prompt_injection_submit_has_test_case(self):
        """denied_prompt_injection_submit must have test_case with injection pattern."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_prompt_injection_submit"),
            None,
        )
        assert site is not None, "denied_prompt_injection_submit not found"
        assert "test_case" in site, "Must have test_case"
        assert "prompt_with_injection" in site["test_case"], "Must have prompt_with_injection"

    def test_denied_hidden_field_unknown_has_test_case(self):
        """denied_hidden_field_unknown must have test_case explaining validation failure."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site = next(
            (s for s in data["submit_sites"] if s["site_id"] == "denied_hidden_field_unknown"),
            None,
        )
        assert site is not None, "denied_hidden_field_unknown not found"
        assert "test_case" in site, "Must have test_case"
        assert "issue" in site["test_case"], "Must describe the issue"


class TestBrowserSubmitPolicySecurityFields:
    """Validate security-critical fields."""

    def test_no_password_fields_in_allowed_origins(self):
        """No test case should have 'password' in allowed_origins."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            for origin in site.get("allowed_origins", []):
                assert "password" not in origin.lower(), f"Password in origin: {origin}"
                assert "pwd" not in origin.lower(), f"pwd in origin: {origin}"

    def test_no_token_in_allowed_origins(self):
        """No test case should have 'token' in allowed_origins."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            for origin in site.get("allowed_origins", []):
                assert "token" not in origin.lower(), f"Token in origin: {origin}"

    def test_no_api_key_in_allowed_origins(self):
        """No test case should have 'api_key' or 'secret' in allowed_origins."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            for origin in site.get("allowed_origins", []):
                assert "api_key" not in origin.lower(), f"api_key in origin: {origin}"
                assert "secret" not in origin.lower(), f"secret in origin: {origin}"


class TestBrowserSubmitPolicyExternalSiteDomains:
    """Validate that no real external business domains are in fixture."""

    REAL_EXTERNAL_DOMAINS = {
        # Payment/Banking
        "naver.com",
        "kakao.com",
        "google.com",
        "amazon.com",
        "paypal.com",
        "stripe.com",
        "toss.im",
        "shinhan.com",
        "kb.co.kr",
        "woori.co.kr",
        "hana.co.kr",
        # Corporate
        "linkedin.com",
        "slack.com",
        "github.com",
        "gitlab.com",
        # Government
        "g2b.go.kr",
        "e-biz.go.kr",
        "nps.or.kr",
    }

    def test_no_real_external_domains_in_allowed_origins(self):
        """Fixture must not contain real external business domains."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            for origin in site.get("allowed_origins", []):
                # Extract domain from URL
                domain = origin.lower().replace("https://", "").replace("http://", "").split("/")[0]
                assert domain not in self.REAL_EXTERNAL_DOMAINS, (
                    f"Real external domain found in {site['site_id']}: {domain}"
                )

    def test_no_real_external_domains_in_test_cases(self):
        """Fixture test_cases must not contain real external business domains."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            if "test_case" in site and "url" in site["test_case"]:
                url = site["test_case"]["url"].lower()
                domain = url.replace("https://", "").replace("http://", "").split("/")[0]
                assert domain not in self.REAL_EXTERNAL_DOMAINS, (
                    f"Real external domain found in test_case of {site['site_id']}: {domain}"
                )


class TestBrowserSubmitPolicySensitiveDataAbsence:
    """Validate that no sensitive data (password, token, secret) appears in fixture."""

    SENSITIVE_KEYWORDS = {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "session_token",
        "refresh_token",
        "secret",
        "api_secret",
        "client_secret",
        "key",
        "api_key",
        "credential",
        "auth",
        "credit_card",
        "cvv",
        "ccv",
        "ssn",
        "pin",
        "otp",
    }

    def test_no_actual_passwords_in_fixture(self):
        """Fixture must not contain actual password values."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            content = f.read()

        # Look for patterns like "password123", "token_abcd1234", etc.
        # (This is a basic check; real code would use more sophisticated patterns)
        assert "123456" not in content.lower(), "Found potential password value"
        assert "abcdef0123456789" not in content.lower(), "Found potential token value"

    def test_no_sensitive_field_values_in_test_cases(self):
        """Fixture test_cases must not contain actual sensitive field values."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for site in data["submit_sites"]:
            if "test_case" in site:
                test_case_str = json.dumps(site["test_case"]).lower()
                for keyword in self.SENSITIVE_KEYWORDS:
                    # Should only see the keyword, not keyword=actual_value
                    # (e.g., "password": "actual_password" would be flagged)
                    # This is a simple check for obvious patterns
                    if keyword in test_case_str:
                        # If the keyword appears, it should be in context like
                        # "password_field_present" or "includes_password", not "password123"
                        assert not (
                            keyword in test_case_str
                            and any(
                                c.isdigit()
                                for c in test_case_str[test_case_str.index(keyword) : test_case_str.index(keyword) + 50]
                            )
                        ), f"Found suspicious pattern with {keyword}"


class TestBrowserSubmitPolicyNoActualSubmitImplementation:
    """Validate that this design does NOT include actual submit implementation."""

    def test_no_submit_function_implementation_exists(self):
        """This test verifies the design contains no actual submit() function."""
        # Check that the fixture only defines policy structure, not execution code
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # The fixture should only be JSON data, no Python functions
        assert isinstance(data, dict), "Fixture must be pure data (JSON)"
        # Verify no "submit_function" or "handler" keys that would indicate code
        for site in data["submit_sites"]:
            assert "submit_function" not in site, "Must not contain submit function implementation"
            assert "handler" not in site, "Must not contain handler implementation"

    def test_no_browser_execution_calls(self):
        """Design must not contain browser execution API calls."""
        # Read the design document
        design_path = Path(__file__).parent.parent.parent / "docs" / "design" / "browser_submit_policy_design_20260506.md"
        if not design_path.exists():
            pytest.skip("Design document not found")

        with design_path.open("r", encoding="utf-8") as f:
            content = f.read()

        # Should NOT contain actual implementation code
        assert "browser.submit(" not in content, "Design must not contain actual submit() call"
        assert "click_submit(" not in content, "Design must not contain actual click_submit() call"
        assert "playwright" not in content.lower() or "playwright backend" in content.lower(), (
            "Design should not reference actual Playwright execution"
        )


class TestBrowserSubmitPolicyCompletenessCriteria:
    """Validate that the design meets completeness criteria."""

    def test_fixture_has_at_least_one_allowed_case(self):
        """Fixture must have at least one allowed case for positive testing."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        allowed_cases = [s for s in data["submit_sites"] if s.get("active") and s["allowed_intents"]]
        assert len(allowed_cases) >= 1, "Fixture must have at least one allowed test case"

    def test_fixture_has_multiple_denied_cases(self):
        """Fixture must have multiple denied cases for comprehensive testing."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        denied_cases = [
            s for s in data["submit_sites"] if not s.get("active") or not s["allowed_intents"] or "reason_denied" in s
        ]
        assert len(denied_cases) >= 3, "Fixture must have at least 3 denied test cases"

    def test_fixture_covers_key_denial_reasons(self):
        """Fixture must cover key denial reasons from design doc."""
        with FIXTURE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        site_ids = {s["site_id"] for s in data["submit_sites"]}

        # Must cover these categories
        assert "denied_unknown_origin" in site_ids, "Must test unknown origin denial"
        assert any("login" in sid for sid in site_ids), "Must test login form denial"
        assert any("payment" in sid or "delete" in sid for sid in site_ids), "Must test destructive action denial"
        assert any("prompt_injection" in sid for sid in site_ids), "Must test prompt injection denial"
        assert any("hidden_field" in sid for sid in site_ids), "Must test hidden field validation denial"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
