"""
서버 브라우저 경계 정책 테스트 (2026-05-07)

테스트 대상:
- ai_orchestrator/browser_tool/policy/server_browser_boundary_policy.py

정책:
- 제한 사이트(은행/카드/세무/정부/보험/인증서) → 서버 브라우저 금지
- Google accounts → BLOCK
- Google 서비스 → API connector 필요
- G2B 공개 read-only만 → 서버 브라우저 허용
- safe_to_execute 항상 False
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
"""

from __future__ import annotations

import json
import pathlib

import pytest

from ai_orchestrator.browser_tool.policy.server_browser_boundary_policy import (
    DECISION_BLOCK,
    DECISION_REQUIRE_API_CONNECTOR,
    DECISION_REQUIRE_LOCAL_AGENT,
    DECISION_REQUIRE_USER_PRESENT,
    DECISION_SERVER_BROWSER_ALLOWED_READONLY,
    classify_restricted_site_for_server_browser,
    evaluate_server_browser_allowed,
    validate_server_browser_boundary_result,
)

FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "local_agent_server_boundary_policy_20260507.json"


@pytest.fixture(scope="session")
def fixture_data():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ── Fixture 기본 검증 ─────────────────────────────────────────────────────────


class TestFixture:
    def test_fixture_file_exists(self):
        assert FIXTURE_PATH.exists()

    def test_fixture_has_minimum_cases(self, fixture_data):
        assert len(fixture_data["cases"]) >= 18

    def test_all_cases_have_required_fields(self, fixture_data):
        required = ["id", "input", "expected_boundary_policy", "expected_execution_location"]
        for case in fixture_data["cases"]:
            for field in required:
                assert field in case, f"case '{case.get('id')}' 누락 필드: {field}"

    def test_all_cases_safe_to_execute_false_in_expected(self, fixture_data):
        for case in fixture_data["cases"]:
            assert case["expected_boundary_policy"].get("safe_to_execute") is False, (
                f"case '{case.get('id')}' expected safe_to_execute should be False"
            )


# ── G2B 공개 read-only ────────────────────────────────────────────────────────


class TestG2BPublicReadonly:
    def test_g2b_public_readonly_server_browser_allowed(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "g2b_public_readonly",
                "target_domain": "www.g2b.go.kr",
                "operation_type": "read",
            }
        )
        assert result["server_browser_decision"] == DECISION_SERVER_BROWSER_ALLOWED_READONLY
        assert result["server_browser_allowed"] is True

    def test_g2b_safe_to_execute_false(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "g2b_public_readonly",
                "target_domain": "www.g2b.go.kr",
            }
        )
        assert result["safe_to_execute"] is False


# ── Google accounts BLOCK ─────────────────────────────────────────────────────


class TestGoogleAccounts:
    def test_google_accounts_domain_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "google",
                "target_domain": "accounts.google.com",
                "target_url": "https://accounts.google.com/signin",
            }
        )
        assert result["server_browser_decision"] == DECISION_BLOCK
        assert result["server_browser_allowed"] is False

    def test_google_accounts_safe_to_execute_false(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "google",
                "target_domain": "accounts.google.com",
            }
        )
        assert result["safe_to_execute"] is False


# ── Google 서비스 → API connector ─────────────────────────────────────────────


class TestGoogleServices:
    def test_gmail_requires_api_connector(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "gmail",
                "target_domain": "mail.google.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_API_CONNECTOR
        assert result["server_browser_allowed"] is False

    def test_google_drive_requires_api_connector(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "google_drive",
                "target_domain": "drive.google.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_API_CONNECTOR

    def test_google_calendar_requires_api_connector(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "google_calendar",
                "target_domain": "calendar.google.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_API_CONNECTOR

    def test_cloud_service_requires_api_connector(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "cloud_service",
                "target_domain": "api.google.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_API_CONNECTOR

    def test_google_workspace_requires_api_connector(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "google_workspace",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_API_CONNECTOR


# ── 은행/카드/세무/정부/보험/인증서 → 서버 브라우저 금지 ──────────────────────


class TestRestrictedCategories:
    @pytest.mark.parametrize(
        "category", ["bank", "card", "tax", "hometax", "government", "gov24", "insurance", "four_insurance"]
    )
    def test_restricted_category_server_browser_blocked(self, category):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": category,
                "target_domain": "example.com",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_bank_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "target_domain": "banking.kbstar.com",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_card_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "card",
                "target_domain": "card.kbstar.com",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_hometax_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "tax",
                "target_domain": "www.hometax.go.kr",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_gov24_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "government",
                "target_domain": "www.gov.kr",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_four_insurance_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "insurance",
                "target_domain": "www.4insure.or.kr",
            }
        )
        assert result["server_browser_allowed"] is False

    def test_certificate_portal_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "certificate",
                "requires_certificate": True,
            }
        )
        assert result["server_browser_allowed"] is False
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT


# ── 인증 요구사항 기반 판정 ───────────────────────────────────────────────────


class TestAuthRequirements:
    def test_otp_required_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_otp": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT
        assert result["server_browser_allowed"] is False

    def test_captcha_required_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_captcha": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_BLOCK
        assert result["server_browser_allowed"] is False

    def test_security_plugin_required_server_browser_blocked(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_security_plugin": True,
            }
        )
        assert result["server_browser_allowed"] is False

    def test_certificate_required_requires_user_present(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_certificate": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT

    def test_financial_certificate_requires_user_present(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_financial_certificate": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT

    def test_password_required_requires_user_present(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_password": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT


# ── 로컬 Agent 및 user-present ────────────────────────────────────────────────


class TestLocalAgentAndUserPresent:
    def test_local_agent_execution_allowed_for_restricted_readonly(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "execution_location": "local_agent",
            }
        )
        assert result["server_browser_allowed"] is False
        assert result["server_browser_decision"] == DECISION_REQUIRE_LOCAL_AGENT

    def test_user_present_required_never_server_browser(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "hometax",
                "user_present_required": True,
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT
        assert result["server_browser_allowed"] is False

    def test_unknown_site_defaults_to_local_agent(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "unknown_new_site",
                "target_domain": "unknown.example.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_REQUIRE_LOCAL_AGENT
        assert result["server_browser_allowed"] is False


# ── evaluate_server_browser_allowed ──────────────────────────────────────────


class TestEvaluateServerBrowserAllowed:
    def test_server_browser_execution_location_forces_block(self):
        result = evaluate_server_browser_allowed(
            {
                "site_category": "bank",
                "execution_location": "server_browser",
                "target_domain": "banking.kbstar.com",
            }
        )
        assert result["server_browser_decision"] == DECISION_BLOCK
        assert result["server_browser_allowed"] is False

    def test_server_playwright_runtime_forces_block(self):
        result = evaluate_server_browser_allowed(
            {
                "site_category": "tax",
                "requested_runtime": "server_playwright",
                "target_domain": "www.hometax.go.kr",
            }
        )
        assert result["server_browser_decision"] == DECISION_BLOCK

    def test_evaluate_includes_message_ko(self):
        result = evaluate_server_browser_allowed(
            {
                "site_category": "bank",
            }
        )
        assert "message_ko" in result
        assert result["message_ko"]

    def test_evaluate_safe_to_execute_false(self):
        result = evaluate_server_browser_allowed(
            {
                "site_category": "bank",
            }
        )
        assert result["safe_to_execute"] is False

    def test_evaluate_safe_to_dispatch_false(self):
        result = evaluate_server_browser_allowed(
            {
                "site_category": "bank",
            }
        )
        assert result["safe_to_dispatch"] is False


# ── validate_server_browser_boundary_result ────────────────────────────────────


class TestValidateBoundaryResult:
    def test_valid_result_no_errors(self):
        result = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
            }
        )
        errors = validate_server_browser_boundary_result(result)
        assert errors == []

    def test_missing_required_field_reports_error(self):
        errors = validate_server_browser_boundary_result(
            {
                "server_browser_decision": "BLOCK",
                "server_browser_allowed": False,
            }
        )
        assert any("safe_to_execute" in e for e in errors)

    def test_safe_to_execute_true_reports_error(self):
        errors = validate_server_browser_boundary_result(
            {
                "server_browser_decision": "BLOCK",
                "execution_location_required": "BLOCKED",
                "server_browser_allowed": False,
                "safe_to_execute": True,
            }
        )
        assert any("safe_to_execute" in e for e in errors)

    def test_invalid_decision_reports_error(self):
        errors = validate_server_browser_boundary_result(
            {
                "server_browser_decision": "INVALID_DECISION",
                "execution_location_required": "BLOCKED",
                "server_browser_allowed": False,
                "safe_to_execute": False,
            }
        )
        assert any("server_browser_decision" in e for e in errors)


# ── 상위 정책과의 호환성 ──────────────────────────────────────────────────────


class TestCompatibilityWithExistingPolicies:
    def test_compatible_with_site_compliance_policy(self):
        """site_compliance_policy 결과를 입력으로 받을 수 있는지 확인."""
        from ai_orchestrator.browser_tool.policy.site_compliance_policy import evaluate_site_compliance

        compliance = evaluate_site_compliance({"site_category": "bank", "operation_type": "read"})
        # site_compliance 결과를 boundary_policy 입력으로 사용
        boundary = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "operation_type": "read",
                **{k: v for k, v in compliance.items() if isinstance(v, (str, bool, int))},
            }
        )
        assert boundary["server_browser_allowed"] is False

    def test_compatible_with_site_access_auditor(self):
        """site_access_compatibility_auditor 결과를 입력으로 받을 수 있는지 확인."""
        from ai_orchestrator.browser_tool.policy.site_access_compatibility_auditor import evaluate_site_access_policy

        audit = evaluate_site_access_policy({"site_category": "bank", "action_name": "read"})
        boundary = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                **{k: v for k, v in audit.items() if isinstance(v, (str, bool, int))},
            }
        )
        assert boundary["server_browser_allowed"] is False

    def test_compatible_with_local_agent_user_present_flow(self):
        """local_agent_user_present_flow와 호환 확인."""
        from ai_orchestrator.agent_hub.user_present_flow import evaluate_user_present_requirement

        evaluate_user_present_requirement({"site_category": "bank", "requires_certificate": True})
        boundary = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "requires_certificate": True,
            }
        )
        assert boundary["server_browser_decision"] == DECISION_REQUIRE_USER_PRESENT

    def test_compatible_with_browser_readonly_runtime(self):
        """browser_readonly_runtime과 호환 확인 — 제한 사이트 readonly 결과."""
        from core.agent_runtime.browser.browser_readonly_runtime import evaluate_readonly_browser_permission

        evaluate_readonly_browser_permission(
            {
                "site_category": "bank",
                "operation_type": "read",
                "target_domain": "banking.kbstar.com",
            }
        )
        boundary = classify_restricted_site_for_server_browser(
            {
                "site_category": "bank",
                "target_domain": "banking.kbstar.com",
            }
        )
        assert boundary["server_browser_allowed"] is False


# ── 소스코드 정책 검사 ────────────────────────────────────────────────────────


class TestSourceCodePolicy:
    SOURCE_FILE = (
        pathlib.Path(__file__).parent.parent / "ai_orchestrator" / "browser_tool" / "policy" / "server_browser_boundary_policy.py"
    )

    def _src(self):
        return self.SOURCE_FILE.read_text(encoding="utf-8")

    def test_no_cookie_extraction(self):
        assert "extract_cookie(" not in self._src()
        assert "get_cookies(" not in self._src()

    def test_no_otp_input_code(self):
        assert "input_otp(" not in self._src()
        assert "fill_otp(" not in self._src()

    def test_no_certificate_password_input(self):
        assert "input_certificate_password(" not in self._src()

    def test_no_playwright_click(self):
        assert "page.click(" not in self._src()

    def test_no_playwright_type(self):
        assert "page.type(" not in self._src()

    def test_no_playwright_fill(self):
        assert "page.fill(" not in self._src()

    def test_no_playwright_submit(self):
        assert "page.submit(" not in self._src()

    def test_no_db_write(self):
        assert "db.write(" not in self._src()
        assert "session.commit(" not in self._src()

    def test_safe_to_execute_always_false_in_code(self):
        # safe_to_execute: True 가 없어야 한다
        assert '"safe_to_execute": True' not in self._src()
        assert "'safe_to_execute': True" not in self._src()
