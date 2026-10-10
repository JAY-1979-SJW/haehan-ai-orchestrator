"""Tests for Site Access Compatibility Audit Module."""

import json
from pathlib import Path

from ai_orchestrator.browser_tool.policy.site_access_compatibility_auditor import (
    classify_auth_methods,
    classify_remote_access_restriction,
    evaluate_site_access_policy,
    validate_site_access_audit_result,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "site_access_compatibility_targets_20260507.json"


class TestFixtureCompatibility:
    """Test fixture compatibility."""

    def test_fixture_loads(self):
        """Fixture loads successfully."""
        assert FIXTURE_PATH.exists()
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data["fixture_id"] == "SITE_ACCESS_COMPATIBILITY_AUDIT_1"

    def test_fixture_targets_valid(self):
        """Fixture targets have required fields."""
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)

        for target in data["targets"]:
            assert "site_id" in target
            assert "site_name" in target
            assert "category" in target
            assert "expected_verdict" in target

    def test_fixture_has_minimum_targets(self):
        """Fixture has minimum required targets."""
        with FIXTURE_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["targets"]) >= 14


class TestClassifyAuthMethods:
    """Test authentication method classification."""

    def test_empty_page(self):
        """Empty page returns no methods."""
        result = classify_auth_methods("")
        assert result["detected_methods"] == []
        assert result["requires_certificate"] is False

    def test_detect_certificate(self):
        """Detects public certificate keyword."""
        page = "공동인증서를 사용하여 로그인하세요"
        result = classify_auth_methods(page)
        assert "공동인증서" in result["detected_methods"]
        assert result["requires_certificate"] is True

    def test_detect_financial_certificate(self):
        """Detects financial certificate keyword."""
        page = "금융인증서로 로그인"
        result = classify_auth_methods(page)
        assert "금융인증서" in result["detected_methods"]
        assert result["requires_financial_certificate"] is True

    def test_detect_simple_auth(self):
        """Detects simple authentication."""
        page = "PASS 간편인증으로 로그인"
        result = classify_auth_methods(page)
        assert any("인증" in m for m in result["detected_methods"])

    def test_detect_otp(self):
        """Detects OTP requirement."""
        page = "OTP 일회용비밀번호를 입력하세요"
        result = classify_auth_methods(page)
        assert result["requires_otp"] is True

    def test_detect_captcha(self):
        """Detects CAPTCHA requirement."""
        page = "reCAPTCHA 인증문자를 입력하세요"
        result = classify_auth_methods(page)
        assert result["requires_captcha"] is True

    def test_detect_security_plugin(self):
        """Detects security plugin requirement."""
        page = "보안프로그램 키보드보안이 필요합니다"
        result = classify_auth_methods(page)
        assert result["requires_security_plugin"] is True


class TestClassifyRemoteRestriction:
    """Test remote access restriction classification."""

    def test_empty_page(self):
        """Empty page has no restrictions."""
        result = classify_remote_access_restriction("")
        assert result["blocks_remote_access"] is False

    def test_detect_remote_block(self):
        """Detects remote access block."""
        page = "원격접속이 차단되었습니다"
        result = classify_remote_access_restriction(page)
        assert result["blocks_remote_access"] is True

    def test_detect_local_requirement(self):
        """Detects local PC requirement."""
        page = "로컬 PC에서만 접근 가능합니다"
        result = classify_remote_access_restriction(page)
        assert result["requires_local_pc"] is True


class TestEvaluateSiteAccessPolicy:
    """Test site access policy evaluation."""

    def test_google_service(self):
        """Google service classified as API_REQUIRED."""
        payload = {
            "site_id": "google_gmail",
            "site_name": "Gmail",
            "category": "google_service",
        }
        result = evaluate_site_access_policy(payload)
        assert result["automation_capability"] == "OAUTH_API_ONLY"
        assert result["final_verdict"] == "API_REQUIRED"

    def test_bank_service(self):
        """Bank service requires user present."""
        payload = {
            "site_id": "bank_test",
            "site_name": "은행 로그인",
            "category": "bank_login",
        }
        result = evaluate_site_access_policy(payload)
        assert result["final_verdict"] == "USER_PRESENT_REQUIRED"
        assert result["requires_security_plugin"] is True

    def test_government_service(self):
        """Government service requires local agent."""
        payload = {
            "site_id": "gov_test",
            "site_name": "정부 사이트",
            "category": "government",
        }
        result = evaluate_site_access_policy(payload)
        assert result["final_verdict"] == "LOCAL_AGENT_REQUIRED"
        assert result["requires_certificate"] is True

    def test_procurement_readonly(self):
        """Procurement sites allow readonly."""
        payload = {
            "site_id": "g2b_test",
            "site_name": "G2B 공개 공고",
            "category": "procurement",
        }
        result = evaluate_site_access_policy(payload)
        assert result["final_verdict"] == "SERVER_READONLY_OK"
        assert "read" in result["allowed_operations"]
        assert "submit" in result["blocked_operations"]

    def test_safe_to_execute_false(self):
        """All audit results have safe_to_execute=false."""
        payloads = [
            {"site_id": "g1", "site_name": "Site1", "category": "google_service"},
            {"site_id": "b1", "site_name": "Site2", "category": "bank_login"},
            {"site_id": "p1", "site_name": "Site3", "category": "procurement"},
        ]
        for payload in payloads:
            result = evaluate_site_access_policy(payload)
            assert result["safe_to_execute"] is False


class TestValidateAuditResult:
    """Test audit result validation."""

    def test_valid_result(self):
        """Valid result passes validation."""
        result = {
            "site_id": "test_site",
            "final_verdict": "USER_PRESENT_REQUIRED",
            "automation_capability": "USER_PRESENT_LOCAL_ONLY",
            "safe_to_execute": False,
        }
        errors = validate_site_access_audit_result(result)
        assert errors == []

    def test_missing_site_id(self):
        """Missing site_id fails validation."""
        result = {
            "final_verdict": "USER_PRESENT_REQUIRED",
            "automation_capability": "USER_PRESENT_LOCAL_ONLY",
            "safe_to_execute": False,
        }
        errors = validate_site_access_audit_result(result)
        assert any("site_id" in e for e in errors)

    def test_missing_verdict(self):
        """Missing final_verdict fails validation."""
        result = {
            "site_id": "test",
            "automation_capability": "USER_PRESENT_LOCAL_ONLY",
            "safe_to_execute": False,
        }
        errors = validate_site_access_audit_result(result)
        assert any("final_verdict" in e for e in errors)

    def test_safe_to_execute_true_fails(self):
        """safe_to_execute=true fails validation."""
        result = {
            "site_id": "test",
            "final_verdict": "USER_PRESENT_REQUIRED",
            "automation_capability": "USER_PRESENT_LOCAL_ONLY",
            "safe_to_execute": True,
        }
        errors = validate_site_access_audit_result(result)
        assert any("safe_to_execute" in e for e in errors)


class TestNoForbiddenImports:
    """Test no forbidden imports or operations."""

    def test_no_task_executor_import(self):
        """Module should not import task_executor."""
        import ast
        import inspect

        from ai_orchestrator.browser_tool.policy import site_access_compatibility_auditor

        source = inspect.getsource(site_access_compatibility_auditor)
        tree = ast.parse(source)

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert not any("task_executor" in imp for imp in imports)
        assert not any("dispatcher" in imp for imp in imports)
        assert not any("playwright" in imp for imp in imports)

    def test_no_credential_operations(self):
        """Module should not contain credential input operations."""
        import inspect

        from ai_orchestrator.browser_tool.policy import site_access_compatibility_auditor

        source = inspect.getsource(site_access_compatibility_auditor)

        # Check for forbidden operations
        forbidden = ["input(", ".fill(", ".type(", ".press(", ".click(", ".submit("]
        for keyword in forbidden:
            assert keyword not in source, f"Found forbidden operation: {keyword}"


class TestAuditIntegration:
    """Test integration with existing policies."""

    def test_compatible_with_site_compliance(self):
        """Audit results compatible with site_compliance_policy."""
        payload = {
            "site_id": "bank_test",
            "site_name": "은행",
            "category": "bank_login",
        }
        result = evaluate_site_access_policy(payload)

        # Should not allow server browser automation
        assert "submit" in result["blocked_operations"]
        assert "type" in result["blocked_operations"]

    def test_readonly_operations_match_allowlist(self):
        """Readonly audit results match allowlist expectations."""
        payload = {
            "site_id": "g2b_test",
            "site_name": "G2B",
            "category": "procurement",
        }
        result = evaluate_site_access_policy(payload)

        # Should only allow read operations
        assert "read" in result["allowed_operations"]
        assert "navigate" in result["allowed_operations"]
