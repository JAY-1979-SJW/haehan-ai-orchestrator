"""Tests for Browser Site Compliance Policy Module."""

import json
from pathlib import Path

import pytest

from ai_orchestrator.browser_tool.policy.site_compliance_policy import (
    evaluate_site_compliance,
    get_site_compliance_policy,
    validate_site_compliance_result,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "browser_site_compliance_policy_20260507.json"


class TestGetSiteCompliancePolicy:
    """Test get_site_compliance_policy()."""

    def test_google_accounts_blocked(self):
        """Google accounts login is blocked."""
        policy = get_site_compliance_policy("accounts.google.com")
        assert policy["capability"] == "AUTOMATION_BLOCKED"
        assert policy["browser_automation_allowed"] is False

    def test_gmail_requires_oauth_api(self):
        """Gmail: 현행 정책(5177645b) = CDP 세션 읽기 전용 허용 (OAuth API 필수 아님)."""
        policy = get_site_compliance_policy("mail.google.com")
        assert policy["capability"] == "CDP_READ_ONLY"
        assert policy["api_connector_required"] is False
        assert policy["browser_automation_allowed"] is True
        assert policy["block_reason"] is None

    def test_google_drive_requires_oauth(self):
        """Google Drive requires OAuth."""
        policy = get_site_compliance_policy("drive.google.com")
        assert policy["capability"] == "OAUTH_API_ONLY"
        assert policy["api_connector_required"] is True

    def test_google_calendar_requires_oauth(self):
        """Google Calendar requires OAuth."""
        policy = get_site_compliance_policy("calendar.google.com")
        assert policy["capability"] == "OAUTH_API_ONLY"

    def test_google_docs_requires_oauth(self):
        """Google Docs requires OAuth."""
        policy = get_site_compliance_policy("docs.google.com")
        assert policy["capability"] == "OAUTH_API_ONLY"

    def test_google_sheets_requires_oauth(self):
        """Google Sheets requires OAuth."""
        policy = get_site_compliance_policy("sheets.google.com")
        assert policy["capability"] == "OAUTH_API_ONLY"

    def test_chrome_remote_desktop_official_only(self):
        """Chrome Remote Desktop requires official tool."""
        policy = get_site_compliance_policy("remotedesktop.google.com")
        assert policy["capability"] == "OFFICIAL_REMOTE_SUPPORT_ONLY"
        assert policy["official_remote_support_required"] is True

    def test_unknown_google_service(self):
        """Unknown Google service requires approval."""
        policy = get_site_compliance_policy("unknown.google.com")
        assert policy["capability"] == "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"

    def test_unknown_site_defaults(self):
        """Unknown site uses default policy."""
        policy = get_site_compliance_policy("unknown-site.invalid")
        assert policy["capability"] == "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"
        assert policy["browser_automation_allowed"] is False

    def test_empty_domain(self):
        """Empty domain uses default policy."""
        policy = get_site_compliance_policy("")
        assert policy["capability"] == "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"

    def test_domain_case_insensitive(self):
        """Domain lookup is case insensitive."""
        policy1 = get_site_compliance_policy("MAIL.GOOGLE.COM")
        policy2 = get_site_compliance_policy("mail.google.com")
        assert policy1["capability"] == policy2["capability"]


class TestEvaluateSiteCompliance:
    """Test evaluate_site_compliance()."""

    def test_google_accounts_blocked(self):
        """Google accounts login is blocked."""
        payload = {
            "target_domain": "accounts.google.com",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "production_mode": False,
        }
        result = evaluate_site_compliance(payload)

        assert result["compliance_decision"] == "BLOCK"
        assert result["block_reason"] == "GOOGLE_LOGIN_AUTOMATION_BLOCKED"
        assert result["safe_to_dispatch"] is False

    def test_gmail_cdp_read_only_allows_navigate(self):
        """Gmail(CDP_READ_ONLY): 이동은 ALLOW_BROWSER_READONLY (커밋 5177645b 완화 정책)."""
        payload = {
            "target_domain": "mail.google.com",
            "action_name": "browser.plan_open_url",
            "operation_type": "navigate",
            "production_mode": False,
        }
        result = evaluate_site_compliance(payload)

        assert result["site_capability"] == "CDP_READ_ONLY"
        assert result["compliance_decision"] == "ALLOW_BROWSER_READONLY"
        assert result["api_connector_required"] is False
        assert result["block_reason"] is None
        assert result["safe_to_dispatch"] is True
        assert result["safe_to_execute"] is False
        assert validate_site_compliance_result(result) == []

    @pytest.mark.parametrize("op", ["read", "navigate", "open_url"])
    def test_gmail_read_ops_allowed(self, op):
        result = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": op})
        assert result["compliance_decision"] == "ALLOW_BROWSER_READONLY"
        assert result["safe_to_dispatch"] is True

    @pytest.mark.parametrize(
        "op", ["submit", "type", "fill", "delete", "send", "upload", "click", "download", "unknown_op", ""]
    )
    def test_gmail_write_ops_blocked(self, op):
        result = evaluate_site_compliance({"target_domain": "mail.google.com", "operation_type": op})
        assert result["compliance_decision"] == "BLOCK"
        assert result["block_reason"] == "OPERATION_NOT_ALLOWED_FOR_READONLY_SITE"
        assert result["safe_to_dispatch"] is False

    def test_gmail_production_mode_still_blocked(self):
        result = evaluate_site_compliance(
            {"target_domain": "mail.google.com", "operation_type": "read", "production_mode": True}
        )
        assert result["compliance_decision"] == "BLOCK"
        assert result["block_reason"] == "PRODUCTION_MODE_BLOCKED"

    @pytest.mark.parametrize(
        "domain", ["drive.google.com", "calendar.google.com", "docs.google.com", "sheets.google.com"]
    )
    def test_other_google_services_policy_unchanged(self, domain):
        result = evaluate_site_compliance({"target_domain": domain, "operation_type": "read"})
        assert result["site_capability"] == "OAUTH_API_ONLY"
        assert result["compliance_decision"] == "REQUIRE_API_CONNECTOR"
        assert result["safe_to_dispatch"] is False

    def test_google_login_and_remote_desktop_unchanged(self):
        login = evaluate_site_compliance({"target_domain": "accounts.google.com", "operation_type": "read"})
        assert login["compliance_decision"] == "BLOCK"
        assert login["block_reason"] == "GOOGLE_LOGIN_AUTOMATION_BLOCKED"
        rd = evaluate_site_compliance({"target_domain": "remotedesktop.google.com", "operation_type": "read"})
        assert rd["compliance_decision"] == "REQUIRE_OFFICIAL_REMOTE_SUPPORT"

    def test_browser_readonly_allows_read(self):
        """Browser readonly site allows read operations."""
        payload = {
            "target_domain": "example.com",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "production_mode": False,
        }
        result = evaluate_site_compliance(payload)

        assert result["compliance_decision"] == "ALLOW_BROWSER_READONLY"
        assert result["safe_to_dispatch"] is True

    def test_browser_readonly_blocks_click(self):
        """Browser readonly site blocks click operations."""
        payload = {
            "target_domain": "example.com",
            "action_name": "browser.execute_click",
            "operation_type": "click",
            "production_mode": False,
        }
        result = evaluate_site_compliance(payload)

        assert result["compliance_decision"] == "BLOCK"
        assert result["block_reason"] == "OPERATION_NOT_ALLOWED_FOR_READONLY_SITE"

    def test_contract_allowlist_with_approval(self):
        """Contract allowlist with approval allows dispatch."""
        payload = {
            "target_domain": "partner-site.example.com",
            "action_name": "browser.open_url_controlled",
            "operation_type": "open_url",
            "production_mode": False,
            "site_owner_approval_id": "approval_123",
        }
        # Manually set capability for testing (would come from policy)
        result = evaluate_site_compliance(payload)

        # Without explicit policy definition, unknown site blocks
        assert result["compliance_decision"] == "BLOCK"
        assert result["site_capability"] == "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"

    def test_user_present_local_with_user(self):
        """User present local with user present allows."""
        payload = {
            "target_domain": "secure-site.example.com",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "production_mode": False,
            "user_present": True,
        }
        # Note: secure-site is not predefined, so uses default
        result = evaluate_site_compliance(payload)
        assert result["safe_to_execute"] is False

    def test_production_mode_always_blocks(self):
        """Production mode always blocks."""
        payload = {
            "target_domain": "example.com",
            "action_name": "browser.inspect",
            "operation_type": "read",
            "production_mode": True,
        }
        result = evaluate_site_compliance(payload)

        assert result["compliance_decision"] == "BLOCK"
        assert result["block_reason"] == "PRODUCTION_MODE_BLOCKED"
        assert result["safe_to_dispatch"] is False

    def test_safe_to_execute_always_false(self):
        """safe_to_execute is always false."""
        test_cases = [
            {
                "target_domain": "accounts.google.com",
                "action_name": "browser.inspect",
                "operation_type": "read",
                "production_mode": False,
            },
            {
                "target_domain": "mail.google.com",
                "action_name": "browser.plan_open_url",
                "operation_type": "navigate",
                "production_mode": False,
            },
            {
                "target_domain": "example.com",
                "action_name": "browser.inspect",
                "operation_type": "read",
                "production_mode": False,
            },
        ]

        for payload in test_cases:
            result = evaluate_site_compliance(payload)
            assert result["safe_to_execute"] is False


class TestValidateSiteComplianceResult:
    """Test validate_site_compliance_result()."""

    def test_valid_result(self):
        """Valid result passes validation."""
        result = {
            "compliance_decision": "ALLOW_BROWSER_READONLY",
            "site_capability": "BROWSER_READONLY_ALLOWED",
            "safe_to_execute": False,
        }
        errors = validate_site_compliance_result(result)
        assert errors == []

    def test_safe_to_execute_must_be_false(self):
        """safe_to_execute=true fails validation."""
        result = {
            "compliance_decision": "ALLOW_BROWSER_READONLY",
            "site_capability": "BROWSER_READONLY_ALLOWED",
            "safe_to_execute": True,
        }
        errors = validate_site_compliance_result(result)
        assert any("safe_to_execute" in e for e in errors)

    def test_missing_compliance_decision(self):
        """Missing compliance_decision fails validation."""
        result = {
            "site_capability": "BROWSER_READONLY_ALLOWED",
            "safe_to_execute": False,
        }
        errors = validate_site_compliance_result(result)
        assert any("compliance_decision" in e for e in errors)

    def test_invalid_capability(self):
        """Invalid capability fails validation."""
        result = {
            "compliance_decision": "ALLOW_BROWSER_READONLY",
            "site_capability": "INVALID_CAPABILITY",
            "safe_to_execute": False,
        }
        errors = validate_site_compliance_result(result)
        assert any("site_capability" in e for e in errors)

    def test_invalid_decision(self):
        """Invalid decision fails validation."""
        result = {
            "compliance_decision": "INVALID_DECISION",
            "site_capability": "BROWSER_READONLY_ALLOWED",
            "safe_to_execute": False,
        }
        errors = validate_site_compliance_result(result)
        assert any("compliance_decision" in e for e in errors)


class TestFixtureCompatibility:
    """Test fixture compatibility."""

    def test_fixture_loads(self):
        """Fixture loads successfully."""
        assert FIXTURE_PATH.exists()
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data["fixture_id"] == "BROWSER_SITE_COMPLIANCE_POLICY_1"

    def test_fixture_cases_valid(self):
        """Fixture cases have required structure."""
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)

        for case in data["cases"]:
            assert "case_id" in case
            assert "input" in case
            assert "expected" in case

    def test_all_cases_safe_to_execute_false(self):
        """All fixture cases have safe_to_execute=false in expected."""
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)

        for case in data["cases"]:
            expected = case.get("expected", {})
            safe_exec = expected.get("safe_to_execute")
            if safe_exec is not None:
                assert safe_exec is False, f"Case {case['case_id']}: safe_to_execute should be false"

    def test_fixture_case_count(self):
        """Fixture has expected number of cases."""
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        # Minimum 16 cases expected
        assert len(data["cases"]) >= 16


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_task_executor_import(self):
        """Module should not import task_executor."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.policy import site_compliance_policy

        source = inspect.getsource(site_compliance_policy)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("task_executor" in imp for imp in imports)
        assert not any("dispatcher" in imp for imp in imports)
        assert not any("playwright" in imp for imp in imports)

    def test_no_db_write(self):
        """Module should not write to database."""
        import inspect

        from ai_orchestrator.browser_tool.policy import site_compliance_policy

        source = inspect.getsource(site_compliance_policy)

        # Check for common DB write patterns
        assert "INSERT" not in source
        assert "UPDATE" not in source
        assert "DELETE" not in source
        assert ".save(" not in source
        assert ".delete(" not in source


class TestGooglePolicyEnforcement:
    """Test Google-specific policy enforcement."""

    def test_no_google_login_automation(self):
        """Google login automation is completely blocked."""
        policy = get_site_compliance_policy("accounts.google.com")
        assert policy["capability"] == "AUTOMATION_BLOCKED"
        assert "LOGIN_AUTOMATION_BLOCKED" in policy["block_reason"]

    def test_all_google_services_require_oauth_or_api(self):
        """All Google services require OAuth/API, not browser automation."""
        google_services = [
            "mail.google.com",
            "drive.google.com",
            "calendar.google.com",
            "docs.google.com",
            "sheets.google.com",
        ]

        for service in google_services:
            policy = get_site_compliance_policy(service)
            if service == "mail.google.com":
                # 현행 정책(5177645b): Gmail 만 CDP 세션 읽기 허용으로 완화
                assert policy["capability"] == "CDP_READ_ONLY"
                assert policy["browser_automation_allowed"] is True
                assert policy["api_connector_required"] is False
                continue
            assert policy["capability"] in {"OAUTH_API_ONLY", "API_ONLY"}
            assert policy["browser_automation_allowed"] is False
            assert policy["api_connector_required"] is True

    def test_google_remote_desktop_official_only(self):
        """Chrome Remote Desktop allows only official tool."""
        policy = get_site_compliance_policy("remotedesktop.google.com")
        assert policy["capability"] == "OFFICIAL_REMOTE_SUPPORT_ONLY"
        assert policy["browser_automation_allowed"] is False


class TestPolicyConsistency:
    """Test consistency with existing preflight modules."""

    def test_no_override_of_type_block(self):
        """Site compliance does not override type operation block."""
        # Even if a site allows click, type must still be blocked by action registry
        payload = {
            "target_domain": "example.com",
            "action_name": "browser.execute_type",
            "operation_type": "type",
            "production_mode": False,
        }
        result = evaluate_site_compliance(payload)

        # Site compliance may allow, but action_registry_preflight blocks type
        # This is the expected behavior (defense in depth)
        assert result["safe_to_execute"] is False

    def test_safe_to_dispatch_true_only_when_allowed(self):
        """safe_to_dispatch is true only when compliance allows."""
        allowed_cases = [
            {
                "target_domain": "example.com",
                "action_name": "browser.inspect",
                "operation_type": "read",
                "production_mode": False,
            },
            {
                "target_domain": "mail.google.com",
                "action_name": "browser.inspect",
                "operation_type": "read",
                "production_mode": False,
            },
        ]

        blocked_cases = [
            {
                "target_domain": "accounts.google.com",
                "action_name": "browser.inspect",
                "operation_type": "read",
                "production_mode": False,
            },
            {
                "target_domain": "mail.google.com",
                "action_name": "browser.send",
                "operation_type": "send",
                "production_mode": False,
            },
        ]

        for payload in allowed_cases:
            result = evaluate_site_compliance(payload)
            assert result["safe_to_dispatch"] is True

        for payload in blocked_cases:
            result = evaluate_site_compliance(payload)
            assert result["safe_to_dispatch"] is False
