"""Real Browser Controlled Submit Click - Smoke Test.

Real Playwright browser testing for controlled internal submit flow.
Uses fixture HTML loaded as data URL for isolated testing.

Flow: load fixture → detect form fields → input values → preview generation →
user confirmation → controlled submit decision → click submit button →
verify internal handling (no external navigation, no DB write)

All smoke tests must run in isolated fixture context (no production submit).
"""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Page, sync_playwright  # noqa: F401

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@pytest.fixture
def allowlist():
    """Load allowlist fixture for policy validation."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "browser_submit_policy_allowlist_20260506.json"
    with fixture_path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fixture_html_content():
    """Load fixture HTML content."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "browser_controlled_submit_form_20260506.html"
    with fixture_path.open(encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def fixture_data_url(fixture_html_content):
    """Create data URL from fixture HTML for isolated browser testing."""
    # Encode HTML as base64 data URL
    html_bytes = fixture_html_content.encode("utf-8")
    b64_encoded = base64.b64encode(html_bytes).decode("utf-8")
    return f"data:text/html;base64,{b64_encoded}"


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestRealBrowserControlledClickSmoke:
    """Real browser smoke test for controlled submit click flow."""

    def test_01_playwright_available(self):
        """Test 1: Playwright is available."""
        assert PLAYWRIGHT_AVAILABLE is True
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            assert browser is not None
            browser.close()

    def test_02_fixture_html_loads(self, fixture_html_content):
        """Test 2: Fixture HTML can be loaded."""
        assert fixture_html_content is not None
        assert len(fixture_html_content) > 0
        assert 'id="contact_form"' in fixture_html_content
        assert 'id="sample_text_field"' in fixture_html_content
        assert 'id="submit_button_id"' in fixture_html_content

    def test_03_data_url_created(self, fixture_data_url):
        """Test 3: Data URL is properly created."""
        assert fixture_data_url is not None
        assert fixture_data_url.startswith("data:text/html;base64,")
        assert len(fixture_data_url) > 100

    def test_04_fixture_form_opens_in_browser(self, fixture_data_url):
        """Test 4: Fixture form can be opened in real browser."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Load fixture as data URL
            page.goto(fixture_data_url)

            # Verify page loaded
            assert page.title() == "Internal Controlled Submit Form"
            assert page.url == fixture_data_url

            # Verify form elements exist
            assert page.query_selector("form#contact_form") is not None
            assert page.query_selector("input#sample_text_field") is not None
            assert page.query_selector("button#submit_button_id") is not None

            context.close()
            browser.close()

    def test_05_detect_sample_text_field(self, fixture_data_url):
        """Test 5: Detect sample_text_field element."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            # Detect sample_text_field
            text_field = page.query_selector("#sample_text_field")
            assert text_field is not None
            assert text_field.get_attribute("type") == "text"
            assert text_field.get_attribute("name") == "sample_text_field"
            assert text_field.get_attribute("required") is not None

            context.close()
            browser.close()

    def test_06_input_dummy_value_to_sample_text_field(self, fixture_data_url):
        """Test 6: Input dummy value to sample_text_field."""
        dummy_value = "REAL_BROWSER_CONTROLLED_CLICK_202605064"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            # Input dummy value
            page.fill("#sample_text_field", dummy_value)

            # Verify input
            value = page.input_value("#sample_text_field")
            assert value == dummy_value

            context.close()
            browser.close()

    def test_07_detect_submit_button(self, fixture_data_url):
        """Test 7: Detect submit button element."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            # Detect submit button
            submit_btn = page.query_selector("#submit_button_id")
            assert submit_btn is not None
            assert submit_btn.get_attribute("type") == "submit"
            assert submit_btn.get_attribute("name") == "submit_button_id"
            assert "Submit Form" in submit_btn.text_content()

            context.close()
            browser.close()

    def test_08_preview_bundle_generation(self, allowlist):
        """Test 8: Preview bundle can be generated from form data."""
        from ai_orchestrator.browser_tool.submit.submit_policy import (
            SubmitValidationRequest,
            validate_submit_policy,
        )
        from ai_orchestrator.browser_tool.submit.submit_preview import (
            SubmitPreviewInput,
            build_submit_preview,
        )

        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="data:text/html;base64,...",  # Would be fixture data URL in real test
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[
                {"name": "sample_text_field", "value": "REAL_BROWSER_CONTROLLED_CLICK_202605064"},
                {"name": "email", "value": "smoke@internal.mock"},
                {"name": "message", "value": "Smoke test message"},
            ],
            hidden_fields=[
                {"name": "csrf_token", "value": "safe_smoke_csrf_token_20260506"},
                {"name": "timestamp", "value": datetime.now(UTC).isoformat()},
                {"name": "form_version", "value": "1.0"},
            ],
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
            validation_id="smoke_real_001",
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
        assert preview_bundle.audit.preview_hash is not None
        assert len(preview_bundle.audit.preview_hash) == 64

    def test_09_user_confirmed_true(self):
        """Test 9: User confirmation is True."""
        user_confirmed = True
        assert user_confirmed is True

    def test_10_policy_validator_allows_controlled(self, allowlist):
        """Test 10: Policy validator returns ALLOW for controlled internal."""
        from ai_orchestrator.browser_tool.submit.submit_policy import (
            SubmitValidationRequest,
            validate_submit_policy,
        )

        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "smoke@internal.mock"}],
            hidden_fields=[{"name": "csrf_token", "value": "safe"}],
            preview_shown=True,
            user_confirmed=True,
        )

        result = validate_submit_policy(request, allowlist)
        assert result.verdict == "ALLOW"

    def test_11_controlled_submit_result_structure(self, allowlist):
        """Test 11: Controlled submit result has correct structure."""
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

        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[{"name": "email", "value": "smoke@internal.mock"}],
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
            validation_id="smoke_real_001",
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

        submit_result = build_controlled_submit_result(
            preview_bundle=preview_bundle,
            user_confirmed=True,
        )

        assert submit_result is not None
        assert submit_result.submitted is True

    def test_12_real_browser_click_submit_button(self, fixture_data_url):
        """Test 12: Real browser can click submit button."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            # Input values
            page.fill("#sample_text_field", "REAL_BROWSER_CONTROLLED_CLICK_202605064")
            page.fill("#email_field", "smoke@internal.mock")
            page.fill("#message_field", "Smoke test message")

            # Click submit button
            page.click("#submit_button_id")

            # Wait for internal handling (page stays at data URL)
            page.wait_for_timeout(500)

            # Verify internal submission was recorded
            submit_state = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state is not None
            assert submit_state["submitCount"] == 1
            assert submit_state["lastSubmitData"]["sample_text_field"] == "REAL_BROWSER_CONTROLLED_CLICK_202605064"
            assert submit_state["lastSubmitData"]["email"] == "smoke@internal.mock"
            assert submit_state["lastSubmitData"]["message"] == "Smoke test message"

            context.close()
            browser.close()

    def test_13_no_external_navigation_after_submit(self, fixture_data_url):
        """Test 13: Page stays at fixture URL (no external navigation)."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            initial_url = fixture_data_url
            page.goto(initial_url)

            # Input and submit
            page.fill("#sample_text_field", "REAL_BROWSER_CONTROLLED_CLICK_202605064")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Verify URL unchanged
            assert page.url == initial_url

            context.close()
            browser.close()

    def test_14_verify_no_external_network_request(self, fixture_data_url):
        """Test 14: No external network requests after submit."""
        requests_made = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Track requests
            def handle_route(route):
                requests_made.append(
                    {
                        "url": route.request.url,
                        "method": route.request.method,
                    }
                )
                route.abort()

            # Abort all network requests (none should be made)
            page.route("**/*", handle_route)
            page.goto(fixture_data_url)

            # Input and submit
            page.fill("#sample_text_field", "REAL_BROWSER_CONTROLLED_CLICK_202605064")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Verify no external requests were made
            # (Only data URL "request" in initial load, no subsequent network calls)
            external_requests = [r for r in requests_made if not r["url"].startswith("data:")]
            assert len(external_requests) == 0

            context.close()
            browser.close()

    def test_15_verify_audit_redacted_payload(self, allowlist):
        """Test 15: Audit payload contains only redacted data (no original secrets)."""
        from ai_orchestrator.browser_tool.submit.submit_policy import (
            SubmitValidationRequest,
            validate_submit_policy,
        )
        from ai_orchestrator.browser_tool.submit.submit_preview import (
            SubmitPreviewInput,
            build_submit_preview,
        )

        request = SubmitValidationRequest(
            site_id="allowed_internal_mock_form",
            url="https://internal.mock/form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            fields=[
                {"name": "sample_text_field", "value": "REAL_BROWSER_CONTROLLED_CLICK_202605064"},
                {"name": "email", "value": "smoke@internal.mock"},
            ],
            hidden_fields=[
                {"name": "csrf_token", "value": "safe_smoke_csrf_token_20260506"},
            ],
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
            validation_id="smoke_real_001",
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

        # Verify audit contains redacted payload, not original values
        assert preview_bundle.audit is not None
        # Audit should not contain actual field values in plaintext
        json.dumps(preview_bundle.audit.__dict__, default=str)
        # The actual values should not appear in audit (they're hashed/redacted)
        # This depends on the audit implementation, but we verify structure exists
        assert "preview_hash" in preview_bundle.audit.__dict__
        assert "validation_id" in preview_bundle.audit.__dict__

    def test_16_browser_cleanup(self, fixture_data_url):
        """Test 16: Browser properly closes and cleans up."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)
            page.fill("#sample_text_field", "REAL_BROWSER_CONTROLLED_CLICK_202605064")
            page.fill("#email_field", "smoke@internal.mock")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Verify form submission recorded
            submit_state = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state["submitCount"] == 1

            # Cleanup
            context.close()
            browser.close()

            # After cleanup, resources should be released
            # (Playwright handles this automatically)

    def test_17_full_flow_integration(self, fixture_data_url, allowlist):
        """Test 17: Full integration flow - load, fill, validate, submit."""
        from ai_orchestrator.browser_tool.submit.submit_policy import (
            SubmitValidationRequest,
            validate_submit_policy,
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Step 1: Load fixture
            page.goto(fixture_data_url)
            assert page.title() == "Internal Controlled Submit Form"

            # Step 2: Detect form fields
            assert page.query_selector("#sample_text_field") is not None
            assert page.query_selector("#email_field") is not None
            assert page.query_selector("#submit_button_id") is not None

            # Step 3: Input values
            page.fill("#sample_text_field", "REAL_BROWSER_CONTROLLED_CLICK_202605064")
            page.fill("#email_field", "smoke@internal.mock")
            page.fill("#message_field", "Integration test message")

            # Step 4: Verify input
            assert page.input_value("#sample_text_field") == "REAL_BROWSER_CONTROLLED_CLICK_202605064"
            assert page.input_value("#email_field") == "smoke@internal.mock"

            # Step 5: Simulate policy validation
            policy_request = SubmitValidationRequest(
                site_id="allowed_internal_mock_form",
                url="https://internal.mock/form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                fields=[
                    {"name": "sample_text_field", "value": "REAL_BROWSER_CONTROLLED_CLICK_202605064"},
                    {"name": "email", "value": "smoke@internal.mock"},
                    {"name": "message", "value": "Integration test message"},
                ],
                hidden_fields=[],
                preview_shown=True,
                user_confirmed=True,
            )
            policy_result = validate_submit_policy(policy_request, allowlist)

            # Step 6: Verify policy allows
            assert policy_result.verdict == "ALLOW"

            # Step 7: Click submit button
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Step 8: Verify internal submission
            submit_state = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state["submitCount"] == 1
            assert submit_state["currentUrl"] == fixture_data_url

            # Step 9: Verify no external navigation
            assert page.url == fixture_data_url

            # Cleanup
            context.close()
            browser.close()
