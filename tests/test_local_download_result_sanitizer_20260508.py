"""
download_result_sanitizer 테스트
"""

from core.agent_runtime.runtime.download.download_result_sanitizer import (
    sanitize_download_result,
    validate_sanitized_download_result,
)


class TestSanitizeDownloadResult:
    def test_file_path_removed(self):
        result = sanitize_download_result(
            {
                "task_id": "t1",
                "file_path": "C:/Users/user/Downloads/notice.pdf",
            }
        )
        assert "file_path" not in result or result.get("file_path") in (None, False, "")

    def test_local_path_removed(self):
        result = sanitize_download_result(
            {
                "task_id": "t1",
                "local_path": "/home/user/downloads/file.pdf",
            }
        )
        assert "local_path" not in result or result.get("local_path") in (None, False, "")

    def test_cookie_removed(self):
        result = sanitize_download_result({"task_id": "t1", "cookie": "abc"})
        assert "cookie" not in result or result.get("cookie") in (None, False, "")

    def test_session_removed(self):
        result = sanitize_download_result({"task_id": "t1", "session": "xyz"})
        assert "session" not in result or result.get("session") in (None, False, "")

    def test_password_removed(self):
        result = sanitize_download_result({"task_id": "t1", "password": "pw"})
        assert "password" not in result or result.get("password") in (None, False, "")

    def test_otp_removed(self):
        result = sanitize_download_result({"task_id": "t1", "otp": "123456"})
        assert "otp" not in result or result.get("otp") in (None, False, "")

    def test_cert_password_removed(self):
        result = sanitize_download_result({"task_id": "t1", "certificate_password": "pw"})
        assert "certificate_password" not in result or result.get("certificate_password") in (None, False, "")

    def test_file_content_removed(self):
        result = sanitize_download_result({"task_id": "t1", "file_content": b"binary"})
        assert "file_content" not in result or result.get("file_content") in (None, False, "")

    def test_safe_fields_forced(self):
        result = sanitize_download_result({"task_id": "t1", "sensitive_data_detected": True})
        assert result["sensitive_data_detected"] is False
        assert result["cookie_exported"] is False
        assert result["session_exported"] is False
        assert result["password_collected"] is False
        assert result["otp_collected"] is False
        assert result["certificate_password_collected"] is False
        assert result["storage_state_exported"] is False
        assert result["file_content_exported"] is False
        assert result["local_path_exported"] is False

    def test_files_entries_sanitized(self):
        result = sanitize_download_result(
            {
                "task_id": "t1",
                "files": [
                    {
                        "file_id": "f1",
                        "safe_name": "notice.pdf",
                        "extension": ".pdf",
                        "size_bytes": 1024,
                        "mime_type": "application/pdf",
                        "upload_allowed": True,
                        "blocked_reason": None,
                        "file_path": "C:/sensitive/path/notice.pdf",  # 제거 대상
                        "certificate_file_detected": False,
                    }
                ],
            }
        )
        for entry in result.get("files", []):
            assert "file_path" not in entry

    def test_task_id_preserved(self):
        result = sanitize_download_result({"task_id": "t1"})
        assert result["task_id"] == "t1"

    def test_safe_name_preserved(self):
        result = sanitize_download_result(
            {
                "files": [
                    {
                        "file_id": "f1",
                        "safe_name": "notice.pdf",
                        "extension": ".pdf",
                        "size_bytes": 1024,
                        "mime_type": "application/pdf",
                        "upload_allowed": True,
                        "blocked_reason": None,
                        "certificate_file_detected": False,
                    }
                ]
            }
        )
        assert result["files"][0]["safe_name"] == "notice.pdf"


class TestValidateSanitizedResult:
    def _clean_result(self):
        return {
            "task_id": "t1",
            "sensitive_data_detected": False,
            "cookie_exported": False,
            "session_exported": False,
            "password_collected": False,
            "otp_collected": False,
            "certificate_password_collected": False,
            "storage_state_exported": False,
            "file_content_exported": False,
            "local_path_exported": False,
            "files": [],
        }

    def test_clean_result_no_violations(self):
        violations = validate_sanitized_download_result(self._clean_result())
        assert violations == []

    def test_cookie_violation(self):
        result = self._clean_result()
        result["cookie"] = "abc"
        violations = validate_sanitized_download_result(result)
        assert any("cookie" in v for v in violations)

    def test_file_path_in_files_violation(self):
        result = self._clean_result()
        result["files"] = [{"file_path": "C:/secret/path"}]
        violations = validate_sanitized_download_result(result)
        assert any("file_path" in v for v in violations)

    def test_sensitive_detected_true_violation(self):
        result = self._clean_result()
        result["sensitive_data_detected"] = True
        violations = validate_sanitized_download_result(result)
        assert any("sensitive_data_detected" in v for v in violations)
