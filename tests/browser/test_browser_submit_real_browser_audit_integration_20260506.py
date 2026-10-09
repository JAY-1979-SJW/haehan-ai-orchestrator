"""Real Browser Controlled Submit + Audit Log Integration Test.

Integration test for full flow:
1. Real browser loads fixture HTML
2. User fills form and clicks submit
3. Controlled submit decision made
4. Audit event created
5. Audit event appended to JSONL
6. Audit log reloaded and verified

No production submit, no DB write, tmp_path only.
"""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from ai_orchestrator.browser_tool.approval.submit_audit_log import (
    append_submit_audit_event,
    build_submit_audit_event,
    read_submit_audit_events,
    redact_audit_payload,
)
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
def fixture_html_content():
    """Load fixture HTML content."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "browser_controlled_submit_form_20260506.html"
    with fixture_path.open(encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def fixture_data_url(fixture_html_content):
    """Create data URL from fixture HTML."""
    html_bytes = fixture_html_content.encode("utf-8")
    b64_encoded = base64.b64encode(html_bytes).decode("utf-8")
    return f"data:text/html;base64,{b64_encoded}"


@pytest.fixture
def allowlist():
    """Load allowlist fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "browser_submit_policy_allowlist_20260506.json"
    with fixture_path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
class TestRealBrowserAuditIntegration:
    """Integration test: real browser click → controlled submit → audit log."""

    def test_01_full_flow_real_browser_to_audit_log(self, fixture_data_url, allowlist, tmp_path):
        """Test 1: Full integration flow from browser click to audit log persistence."""
        audit_log_path = tmp_path / "audit.jsonl"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Step 1: Load fixture form
            page.goto(fixture_data_url)
            assert page.title() == "Internal Controlled Submit Form"

            # Step 2: User fills form
            sample_value = "REAL_BROWSER_AUDIT_INTEGRATION_TEST_001"
            email_value = "test@internal.mock"
            message_value = "Integration test message"

            page.fill("#sample_text_field", sample_value)
            page.fill("#email_field", email_value)
            page.fill("#message_field", message_value)

            # Step 3: Create policy validation request
            policy_request = SubmitValidationRequest(
                site_id="allowed_internal_mock_form",
                url="https://internal.mock/form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                fields=[
                    {"name": "sample_text_field", "value": sample_value},
                    {"name": "email", "value": email_value},
                    {"name": "message", "value": message_value},
                ],
                hidden_fields=[
                    {"name": "csrf_token", "value": "safe_token"},
                    {"name": "timestamp", "value": datetime.now(UTC).isoformat()},
                ],
                preview_shown=True,
                user_confirmed=True,
            )

            # Step 4: Validate policy
            policy_result = validate_submit_policy(policy_request, allowlist)
            assert policy_result.verdict == "ALLOW"

            # Step 5: Generate preview
            preview_input = SubmitPreviewInput(
                site_id=policy_request.site_id,
                form_id=policy_request.form_id,
                submit_button_id=policy_request.submit_button_id,
                intent=policy_request.intent,
                fields=policy_request.fields,
                hidden_fields=policy_request.hidden_fields,
                policy_verdict=policy_result.verdict,
                validation_id="audit_int_001",
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
            assert preview_bundle.audit.preview_hash is not None

            # Step 6: Create controlled submit result
            submit_result = build_controlled_submit_result(
                preview_bundle=preview_bundle,
                user_confirmed=True,
            )
            assert submit_result.submit_result == "success"

            # Step 7: Click submit button in real browser
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Step 8: Verify internal submit was recorded
            submit_state = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state["submitCount"] == 1
            assert submit_state["lastSubmitData"]["sample_text_field"] == sample_value

            # Step 9: Create audit event with redacted payload
            redacted_payload = redact_audit_payload(
                {
                    "sample_text_field": sample_value,
                    "email": email_value,
                    "message": message_value,
                    "csrf_token": "safe_token",
                }
            )

            audit_event = build_submit_audit_event(
                validation_id="audit_int_001",
                action_id="browser.submit.controlled_click",
                site_id="allowed_internal_mock_form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                policy_verdict=policy_result.verdict,
                risk_level="high",
                preview_hash=preview_bundle.audit.preview_hash,
                user_confirmed=True,
                submitted=submit_state["submitCount"] > 0,
                submit_result="success",
                redacted_payload=redacted_payload,
                result_summary="Real browser integration test - form submitted successfully",
                approved_by="test_user",
                submit_timestamp=now,
                metadata={
                    "browser": "chromium_headless",
                    "isolation": "data_url",
                    "test_type": "integration",
                },
            )

            # Step 10: Append audit event to JSONL
            write_result = append_submit_audit_event(audit_log_path, audit_event)
            assert write_result.success is True
            assert write_result.event_count == 1

            # Step 11: Reload audit log and verify
            events = read_submit_audit_events(audit_log_path)
            assert len(events) == 1
            assert events[0]["validation_id"] == "audit_int_001"
            assert events[0]["submitted"] is True
            assert events[0]["submit_result"] == "success"
            assert events[0]["preview_hash"] == preview_bundle.audit.preview_hash
            assert events[0]["policy_verdict"] == "ALLOW"

            # Step 12: Verify no raw sensitive data in audit log
            audit_json = json.dumps(events[0])
            assert "safe_token" in audit_json  # Safe hidden field preserved
            assert sample_value in audit_json  # Form field preserved
            assert email_value in audit_json  # Email preserved

            # Step 13: Verify page URL unchanged (no external navigation)
            assert page.url == fixture_data_url

            context.close()
            browser.close()

    def test_02_multiple_submissions_audit_append(self, fixture_data_url, allowlist, tmp_path):
        """Test 2: Multiple browser submissions appended to audit log."""
        audit_log_path = tmp_path / "audit.jsonl"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            # First submission
            page.fill("#sample_text_field", "SUBMISSION_001")
            page.fill("#email_field", "test1@test.com")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            submit_state_1 = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state_1["submitCount"] == 1

            # Create and append first audit event
            audit_event_1 = build_submit_audit_event(
                validation_id="audit_int_002a",
                action_id="browser.submit.controlled_click",
                site_id="allowed_internal_mock_form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                policy_verdict="ALLOW",
                risk_level="high",
                preview_hash="a" * 64,
                user_confirmed=True,
                submitted=True,
                submit_result="success",
                redacted_payload={"email": "test1@test.com"},
                result_summary="First submission",
            )

            result_1 = append_submit_audit_event(audit_log_path, audit_event_1)
            assert result_1.success is True
            assert result_1.event_count == 1

            # Reset form for second submission
            page.click("button.reset-btn")  # Reset button
            page.wait_for_timeout(300)

            # Second submission
            page.fill("#sample_text_field", "SUBMISSION_002")
            page.fill("#email_field", "test2@test.com")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            submit_state_2 = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state_2["submitCount"] == 2

            # Create and append second audit event
            audit_event_2 = build_submit_audit_event(
                validation_id="audit_int_002b",
                action_id="browser.submit.controlled_click",
                site_id="allowed_internal_mock_form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                policy_verdict="ALLOW",
                risk_level="high",
                preview_hash="b" * 64,
                user_confirmed=True,
                submitted=True,
                submit_result="success",
                redacted_payload={"email": "test2@test.com"},
                result_summary="Second submission",
            )

            result_2 = append_submit_audit_event(audit_log_path, audit_event_2)
            assert result_2.success is True
            assert result_2.event_count == 2

            # Reload and verify both events
            events = read_submit_audit_events(audit_log_path)
            assert len(events) == 2
            assert events[0]["validation_id"] == "audit_int_002a"
            assert events[1]["validation_id"] == "audit_int_002b"
            assert events[0]["submitted"] is True
            assert events[1]["submitted"] is True

            context.close()
            browser.close()

    def test_03_audit_event_contains_all_required_fields(self, fixture_data_url, allowlist, tmp_path):
        """Test 3: Audit event from real browser submit has all required fields."""
        audit_log_path = tmp_path / "audit.jsonl"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(fixture_data_url)

            page.fill("#sample_text_field", "COMPLETE_TEST")
            page.fill("#email_field", "complete@test.com")
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Create comprehensive audit event
            audit_event = build_submit_audit_event(
                validation_id="audit_int_003",
                action_id="browser.submit.controlled_click",
                site_id="allowed_internal_mock_form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                policy_verdict="ALLOW",
                risk_level="high",
                preview_hash="c" * 64,
                user_confirmed=True,
                submitted=True,
                submit_result="success",
                redacted_payload={"email": "complete@test.com", "msg": "test"},
                result_summary="Complete test",
                approved_by="integration_tester",
                submit_timestamp=datetime.now(UTC).isoformat(),
                metadata={"test": "complete", "browser": "chromium"},
            )

            # Append and reload
            append_submit_audit_event(audit_log_path, audit_event)
            events = read_submit_audit_events(audit_log_path)

            audit_dict = events[0]

            # Verify all required fields
            assert audit_dict["schema_version"] == "1.0"
            assert audit_dict["event_id"] is not None
            assert audit_dict["created_at"] is not None
            assert audit_dict["validation_id"] == "audit_int_003"
            assert audit_dict["action_id"] == "browser.submit.controlled_click"
            assert audit_dict["site_id"] == "allowed_internal_mock_form"
            assert audit_dict["form_id"] == "contact_form"
            assert audit_dict["submit_button_id"] == "submit_btn"
            assert audit_dict["intent"] == "submit_contact_form"
            assert audit_dict["preview_hash"] == "c" * 64
            assert audit_dict["policy_verdict"] == "ALLOW"
            assert audit_dict["risk_level"] == "high"
            assert audit_dict["user_confirmed"] is True
            assert audit_dict["submitted"] is True
            assert audit_dict["submit_result"] == "success"
            assert audit_dict["redacted_payload"]["email"] == "complete@test.com"
            assert audit_dict["result_summary"] == "Complete test"
            assert audit_dict["approved_by"] == "integration_tester"
            assert audit_dict["approved_at"] is not None
            assert audit_dict["submit_timestamp"] is not None
            assert audit_dict["metadata"]["test"] == "complete"

            context.close()
            browser.close()

    def test_04_no_production_submit_happens(self, fixture_data_url, tmp_path):
        """Test 4: Real browser submit is internal only (no production submit)."""
        audit_log_path = tmp_path / "audit.jsonl"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()

            # Track all network requests to verify no external submit
            requests_made = []

            def handle_route(route):
                requests_made.append(
                    {
                        "url": route.request.url,
                        "method": route.request.method,
                    }
                )
                route.abort()

            page = context.new_page()
            page.route("**/*", handle_route)

            page.goto(fixture_data_url)

            page.fill("#sample_text_field", "NO_PRODUCTION_SUBMIT")
            page.fill("#email_field", "no@production.com")

            # Click submit
            page.click("#submit_button_id")
            page.wait_for_timeout(500)

            # Verify form submission was internal only
            submit_state = page.evaluate("() => window.SMOKE_TEST_FORM_STATE")
            assert submit_state["submitCount"] == 1

            # Verify no external network requests
            external_requests = [r for r in requests_made if not r["url"].startswith("data:")]
            assert len(external_requests) == 0, f"External requests detected: {external_requests}"

            # Create audit event showing internal-only submission
            audit_event = build_submit_audit_event(
                validation_id="audit_int_004",
                action_id="browser.submit.controlled_click",
                site_id="allowed_internal_mock_form",
                form_id="contact_form",
                submit_button_id="submit_btn",
                intent="submit_contact_form",
                policy_verdict="ALLOW",
                risk_level="high",
                preview_hash="d" * 64,
                user_confirmed=True,
                submitted=True,
                submit_result="success",
                redacted_payload={"email": "no@production.com"},
                result_summary="Internal submission only (no external navigation)",
            )

            write_result = append_submit_audit_event(audit_log_path, audit_event)
            assert write_result.success is True

            # Verify in audit log
            events = read_submit_audit_events(audit_log_path)
            assert events[0]["result_summary"] == "Internal submission only (no external navigation)"

            context.close()
            browser.close()

    def test_05_audit_log_redaction_complete(self, fixture_data_url, tmp_path):
        """Test 5: Audit log contains no raw sensitive data."""
        audit_log_path = tmp_path / "audit.jsonl"

        sensitive_payload = {
            "email": "user@test.com",
            "password": "secret123",  # Should be masked
            "api_token": "token_xyz789",  # Should be masked
            "csrf_token": "safe_csrf_123",  # Should be preserved
            "form_version": "1.0",  # Should be preserved
        }

        redacted = redact_audit_payload(sensitive_payload)

        audit_event = build_submit_audit_event(
            validation_id="audit_int_005",
            action_id="browser.submit.controlled_click",
            site_id="allowed_internal_mock_form",
            form_id="contact_form",
            submit_button_id="submit_btn",
            intent="submit_contact_form",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="e" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload=redacted,
            result_summary="Redaction test",
        )

        append_submit_audit_event(audit_log_path, audit_event)
        events = read_submit_audit_events(audit_log_path)

        # Verify in JSON
        audit_json = json.dumps(events[0])

        # Raw sensitive values should NOT be in audit log
        assert "secret123" not in audit_json
        assert "token_xyz789" not in audit_json

        # Safe values should be in audit log
        assert "safe_csrf_123" in audit_json
        assert "1.0" in audit_json
        assert "user@test.com" in audit_json

        # Masked fields should have marker
        assert redacted["password"] == {"masked": True}
        assert redacted["api_token"] == {"masked": True}

    def test_06_tmp_path_only_no_production_paths(self, tmp_path):
        """Test 6: All file operations use tmp_path (no production paths)."""
        audit_log_path = tmp_path / "audit.jsonl"

        # Verify path is in tmp_path
        assert str(tmp_path) in str(audit_log_path)
        assert "/var/log" not in str(audit_log_path)
        assert "C:\\Program Files" not in str(audit_log_path).lower()

        # Create and verify file is in tmp_path
        audit_event = build_submit_audit_event(
            validation_id="audit_int_006",
            action_id="browser.submit.controlled_click",
            site_id="site1",
            form_id="form1",
            submit_button_id="btn1",
            intent="intent1",
            policy_verdict="ALLOW",
            risk_level="high",
            preview_hash="f" * 64,
            user_confirmed=True,
            submitted=True,
            submit_result="success",
            redacted_payload={},
            result_summary="Path test",
        )

        result = append_submit_audit_event(audit_log_path, audit_event)
        assert result.success is True
        assert str(tmp_path) in str(result.path)
