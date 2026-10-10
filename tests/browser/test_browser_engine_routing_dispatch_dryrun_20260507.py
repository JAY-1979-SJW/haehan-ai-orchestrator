"""
Browser Engine Routing Dispatch Dryrun Integration 테스트

safe_to_execute: 항상 False.
dry_run: 항상 True.
실제 브라우저/Playwright/API 접근 없음.
"""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun import (
    DISPATCH_API_CONNECTOR_REQUIRED,
    DISPATCH_APPROVAL_REQUIRED,
    DISPATCH_BLOCKED,
    DISPATCH_DOMAIN_VERIFICATION_REQUIRED,
    DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY,
    DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
    DISPATCH_MANUAL_REVIEW_REQUIRED,
    DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY,
    build_dryrun_dispatch_context,
    evaluate_browser_engine_routing_dispatch_dryrun,
    validate_dryrun_dispatch_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_engine_routing_dispatch_dryrun_20260507.json"


@pytest.fixture(scope="module")
def fixture_cases():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)["cases"]


# ── fixture 케이스 기반 테스트 ────────────────────────────────────────────────


class TestFixtureCases:
    def test_about_blank_server_readonly_ready(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "about_blank_server_readonly_ready")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]
        assert result["ok"] == case["expected_ok"]

    def test_example_com_server_readonly_ready(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "example_com_server_readonly_ready")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]
        assert result["ok"] == case["expected_ok"]

    def test_g2b_server_readonly_ready(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "g2b_server_readonly_ready")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]
        assert result["ok"] == case["expected_ok"]

    def test_bank_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "bank_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]
        assert result["ok"] is False

    def test_card_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "card_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_hometax_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "hometax_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_gov24_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "gov24_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_four_insurance_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "four_insurance_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_certificate_portal_local_system_browser_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "certificate_portal_local_system_browser_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_google_accounts_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "google_accounts_blocked")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_BLOCKED
        assert result["ok"] is False

    def test_gmail_api_connector_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "gmail_api_connector_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_API_CONNECTOR_REQUIRED
        assert result["ok"] is False

    def test_drive_api_connector_required(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "drive_api_connector_required")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_API_CONNECTOR_REQUIRED

    def test_captcha_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "captcha_blocked")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_BLOCKED
        assert result["ok"] is False

    def test_unknown_site_manual_review(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "unknown_site_manual_review")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_MANUAL_REVIEW_REQUIRED
        assert result["ok"] is False

    def test_production_mode_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "production_mode_blocked")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_BLOCKED
        assert result["ok"] is False

    def test_type_operation_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "type_operation_blocked")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_BLOCKED

    def test_submit_operation_blocked(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "submit_operation_blocked")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_BLOCKED

    def test_approval_required_stops_dispatch(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "approval_required_stops_dispatch")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_APPROVAL_REQUIRED
        assert result["ok"] is False

    def test_policy_blocked_no_fallback_dispatch(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "policy_blocked_no_fallback_dispatch")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED

    def test_runtime_failure_local_agent_fallback(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "runtime_failure_local_agent_fallback")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_server_allowed_runtime_failure_fallback_available(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "server_allowed_runtime_failure_fallback_available")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        assert result["dispatch_decision"] == case["expected_dispatch_decision"]

    def test_all_fields_present_in_result(self, fixture_cases):
        case = next(c for c in fixture_cases if c["id"] == "all_fields_present_in_result")
        result = evaluate_browser_engine_routing_dispatch_dryrun(case["input"])
        for field in case["expected_fields"]:
            assert field in result, f"필수 필드 누락: {field}"


# ── dry_run / safe_to_execute 불변 속성 테스트 ─────────────────────────────────


class TestInvariantProperties:
    def test_dry_run_always_true(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert result["dry_run"] is True

    def test_safe_to_execute_always_false(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert result["safe_to_execute"] is False

    def test_safe_to_execute_false_on_blocked(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {
                "site_category": "bank",
                "target_domain": "kbstar.com",
                "operation_type": "read",
                "requires_certificate": True,
                "production_mode": False,
            }
        )
        assert result["safe_to_execute"] is False

    def test_dry_run_true_on_blocked(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "type", "production_mode": False}
        )
        assert result["dry_run"] is True

    def test_ok_false_on_non_server_playwright(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {
                "site_category": "gmail",
                "target_domain": "mail.google.com",
                "target_url": "https://mail.google.com/",
                "operation_type": "read",
                "production_mode": False,
            }
        )
        assert result["ok"] is False

    def test_ok_true_only_for_server_playwright_ready(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert result["ok"] is True
        assert result["dispatch_decision"] == DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY


# ── dispatch_decision enum 유효성 테스트 ──────────────────────────────────────


class TestDispatchDecisionEnum:
    def test_server_playwright_ready_enum(self):
        assert DISPATCH_SERVER_PLAYWRIGHT_READONLY_READY == "DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY"

    def test_local_agent_ready_enum(self):
        assert DISPATCH_LOCAL_AGENT_PLAYWRIGHT_READY == "DRYRUN_LOCAL_AGENT_PLAYWRIGHT_READY"

    def test_local_system_browser_enum(self):
        assert (
            DISPATCH_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED == "DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED"
        )

    def test_api_connector_enum(self):
        assert DISPATCH_API_CONNECTOR_REQUIRED == "DRYRUN_API_CONNECTOR_REQUIRED"

    def test_approval_required_enum(self):
        assert DISPATCH_APPROVAL_REQUIRED == "DRYRUN_APPROVAL_REQUIRED"

    def test_domain_verification_enum(self):
        assert DISPATCH_DOMAIN_VERIFICATION_REQUIRED == "DRYRUN_DOMAIN_VERIFICATION_REQUIRED"

    def test_blocked_enum(self):
        assert DISPATCH_BLOCKED == "DRYRUN_BLOCKED"

    def test_manual_review_enum(self):
        assert DISPATCH_MANUAL_REVIEW_REQUIRED == "DRYRUN_MANUAL_REVIEW_REQUIRED"


# ── validate_dryrun_dispatch_result 테스트 ─────────────────────────────────────


class TestValidateResult:
    def test_valid_result_no_errors(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        errors = validate_dryrun_dispatch_result(result)
        assert errors == []

    def test_missing_field_detected(self):
        errors = validate_dryrun_dispatch_result({"dry_run": True, "safe_to_execute": False})
        assert any("필수 필드 누락" in e for e in errors)

    def test_dry_run_false_detected(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        result["dry_run"] = False
        errors = validate_dryrun_dispatch_result(result)
        assert any("dry_run" in e for e in errors)

    def test_safe_to_execute_true_detected(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        result["safe_to_execute"] = True
        errors = validate_dryrun_dispatch_result(result)
        assert any("safe_to_execute" in e for e in errors)


# ── build_dryrun_dispatch_context 테스트 ──────────────────────────────────────


class TestBuildContext:
    def test_context_contains_chain_result(self):
        ctx = build_dryrun_dispatch_context(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert "chain_result" in ctx
        assert ctx["dry_run"] is True

    def test_context_chain_result_has_next_step(self):
        ctx = build_dryrun_dispatch_context(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert "next_step" in ctx["chain_result"]


# ── 보안 원칙 준수 테스트 ─────────────────────────────────────────────────────


class TestSecurityPrinciples:
    def test_no_actual_browser_execution_in_source(self):
        import inspect

        import ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun as mod

        src = inspect.getsource(mod)
        forbidden = ["playwright.chromium.launch", "page.goto(", "page.click(", "page.fill("]
        for token in forbidden:
            assert token not in src, f"금지된 코드 발견: {token}"

    def test_no_cookie_session_extraction_in_source(self):
        import inspect

        import ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun as mod

        src = inspect.getsource(mod)
        forbidden = ["cookies()", "storage_state(", "session_token"]
        for token in forbidden:
            assert token not in src, f"금지된 코드 발견: {token}"

    def test_no_task_executor_in_source(self):
        import inspect

        import ai_orchestrator.browser_tool.routing.browser_engine_routing_dispatch_dryrun as mod

        src = inspect.getsource(mod)
        assert "TaskExecutor(" not in src

    def test_result_field_contains_preflight_decisions(self):
        result = evaluate_browser_engine_routing_dispatch_dryrun(
            {"target_url": "about:blank", "operation_type": "read", "production_mode": False}
        )
        assert "site_compliance_decision" in result["result"]
        assert "server_boundary_decision" in result["result"]
        assert "action_preflight_decision" in result["result"]
        assert "gate_preflight_decision" in result["result"]
        assert "allowlist_decision" in result["result"]
