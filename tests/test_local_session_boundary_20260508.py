"""
local_session_boundary 테스트
"""

from core.agent_runtime.runtime.local_session_boundary import (
    enforce_session_boundary,
    get_boundary_safe_defaults,
    is_safe_for_export,
    validate_session_boundary,
)


class TestEnforceSessionBoundary:
    def test_cookie_removed(self):
        result = enforce_session_boundary({"ok": True, "cookie": "abc123"})
        assert result.get("cookie") in (None,)
        assert "cookie" not in result or result["cookie"] in (None, False, "")

    def test_session_removed(self):
        result = enforce_session_boundary({"ok": True, "session": "sess123"})
        assert "session" not in result or result["session"] in (None, False, "")

    def test_password_removed(self):
        result = enforce_session_boundary({"ok": True, "password": "pw123"})
        assert "password" not in result or result["password"] in (None, False, "")

    def test_otp_removed(self):
        result = enforce_session_boundary({"ok": True, "otp": "123456"})
        assert "otp" not in result or result["otp"] in (None, False, "")

    def test_safe_fields_forced(self):
        result = enforce_session_boundary({"ok": True})
        assert result["cookie_exported"] is False
        assert result["session_exported"] is False
        assert result["password_collected"] is False
        assert result["otp_collected"] is False
        assert result["certificate_password_collected"] is False
        assert result["sensitive_data_collected"] is False
        assert result["storage_state_exported"] is False

    def test_storage_state_removed(self):
        result = enforce_session_boundary({"ok": True, "storage_state": {"cookies": []}})
        assert "storage_state" not in result or result.get("storage_state") in (None, False)

    def test_npki_removed(self):
        result = enforce_session_boundary({"ok": True, "npki": "path/to/cert"})
        assert "npki" not in result or result.get("npki") in (None, False, "")

    def test_certificate_password_removed(self):
        result = enforce_session_boundary({"ok": True, "certificate_password": "pw"})
        assert "certificate_password" not in result or result.get("certificate_password") in (None, False, "")

    def test_extracted_data_cleaned(self):
        result = enforce_session_boundary(
            {
                "ok": True,
                "extracted_data": {"body_text": "ok", "cookie": "abc"},
            }
        )
        assert "cookie" not in result["extracted_data"]
        assert result["extracted_data"]["body_text"] == "ok"

    def test_safe_fields_not_overrideable(self):
        result = enforce_session_boundary(
            {
                "ok": True,
                "sensitive_data_collected": True,  # 강제 덮어쓰기
            }
        )
        assert result["sensitive_data_collected"] is False


class TestValidateSessionBoundary:
    def test_clean_result_no_violations(self):
        result = {
            "ok": True,
            "cookie_exported": False,
            "session_exported": False,
            "password_collected": False,
            "otp_collected": False,
            "certificate_password_collected": False,
            "sensitive_data_collected": False,
            "storage_state_exported": False,
        }
        violations = validate_session_boundary(result)
        assert violations == []

    def test_cookie_exported_true_is_violation(self):
        result = get_boundary_safe_defaults()
        result["cookie_exported"] = True
        violations = validate_session_boundary(result)
        assert any("cookie_exported" in v for v in violations)

    def test_password_field_present_is_violation(self):
        result = get_boundary_safe_defaults()
        result["password"] = "secret"
        violations = validate_session_boundary(result)
        assert any("password" in v for v in violations)


class TestIsSafeForExport:
    def test_safe_result_is_exportable(self):
        result = get_boundary_safe_defaults()
        result["ok"] = True
        assert is_safe_for_export(result) is True

    def test_result_with_cookie_not_exportable(self):
        result = get_boundary_safe_defaults()
        result["cookie"] = "abc"
        assert is_safe_for_export(result) is False

    def test_result_with_session_exported_true_not_exportable(self):
        result = get_boundary_safe_defaults()
        result["session_exported"] = True
        assert is_safe_for_export(result) is False
