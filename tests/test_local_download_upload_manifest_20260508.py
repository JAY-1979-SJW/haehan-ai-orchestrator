"""
download_upload_manifest + server upload policy 통합 테스트
"""

from ai_orchestrator.agent_hub.policy.file_upload_policy import (
    get_server_upload_policy_summary,
    validate_upload_manifest,
)
from core.agent_runtime.runtime.download.download_upload_manifest import (
    build_manifest,
    is_safe_manifest,
    validate_manifest,
)

TASK_ID = "manifest-task-001"


def _make_files(*names_sizes):
    return [{"filename": n, "size_bytes": s} for n, s in names_sizes]


class TestBuildManifest:
    def test_pdf_upload_allowed(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "notice.pdf", "size_bytes": 1024}],
            task_downloaded_filenames=["notice.pdf"],
        )
        assert manifest["files"][0]["upload_allowed"] is True

    def test_hwpx_upload_allowed(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "attach.hwpx", "size_bytes": 2048}],
            task_downloaded_filenames=["attach.hwpx"],
        )
        assert manifest["files"][0]["upload_allowed"] is True

    def test_xlsx_upload_allowed(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "data.xlsx", "size_bytes": 512}],
            task_downloaded_filenames=["data.xlsx"],
        )
        assert manifest["files"][0]["upload_allowed"] is True

    def test_exe_blocked(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "setup.exe", "size_bytes": 1024}],
            task_downloaded_filenames=["setup.exe"],
        )
        assert manifest["files"][0]["upload_allowed"] is False

    def test_pfx_blocked_cert_detected(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "cert.pfx", "size_bytes": 1024}],
            task_downloaded_filenames=["cert.pfx"],
        )
        assert manifest["files"][0]["upload_allowed"] is False
        assert manifest["certificate_file_detected"] is True

    def test_npki_path_blocked(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "signCert.der", "size_bytes": 512, "file_path": "C:/NPKI/signCert.der"}],
            task_downloaded_filenames=["signCert.der"],
        )
        assert manifest["files"][0]["upload_allowed"] is False

    def test_password_name_blocked(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "my_password.pdf", "size_bytes": 1024}],
            task_downloaded_filenames=["my_password.pdf"],
        )
        assert manifest["files"][0]["upload_allowed"] is False

    def test_task_external_file_blocked(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "other.pdf", "size_bytes": 1024}],
            task_downloaded_filenames=["notice.pdf"],
        )
        assert manifest["files"][0]["upload_allowed"] is False

    def test_oversized_file_blocked(self):
        from core.agent_runtime.runtime.download.download_policy import MAX_FILE_SIZE_BYTES

        manifest = build_manifest(
            TASK_ID,
            [{"filename": "big.pdf", "size_bytes": MAX_FILE_SIZE_BYTES + 1}],
            task_downloaded_filenames=["big.pdf"],
        )
        assert manifest["files"][0]["upload_allowed"] is False

    def test_manifest_no_sensitive_data(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "notice.pdf", "size_bytes": 1024}],
            task_downloaded_filenames=["notice.pdf"],
        )
        assert manifest["sensitive_data_detected"] is False

    def test_manifest_no_local_path(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "notice.pdf", "size_bytes": 1024, "file_path": "C:/Users/secret/Downloads/notice.pdf"}],
            task_downloaded_filenames=["notice.pdf"],
        )
        for entry in manifest["files"]:
            assert "file_path" not in entry
            assert "local_path" not in entry

    def test_manifest_no_cookie(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        assert "cookie" not in manifest or manifest.get("cookie") in (None, False, "")

    def test_manifest_no_session(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        assert "session" not in manifest or manifest.get("session") in (None, False, "")

    def test_manifest_no_password(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        assert "password" not in manifest or manifest.get("password") in (None, False, "")

    def test_manifest_counts(self):
        files = [
            {"filename": "notice.pdf", "size_bytes": 1024},
            {"filename": "cert.pfx", "size_bytes": 512},
        ]
        manifest = build_manifest(
            TASK_ID,
            files,
            task_downloaded_filenames=["notice.pdf", "cert.pfx"],
        )
        assert manifest["total_files"] == 2
        assert manifest["allowed_count"] == 1
        assert manifest["blocked_count"] == 1

    def test_task_id_preserved(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        assert manifest["task_id"] == TASK_ID


class TestValidateManifest:
    def test_clean_manifest_safe(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "notice.pdf", "size_bytes": 1024}],
            task_downloaded_filenames=["notice.pdf"],
        )
        assert is_safe_manifest(manifest) is True

    def test_manifest_with_local_path_not_safe(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        manifest["files"] = [{"file_path": "C:/secret"}]
        violations = validate_manifest(manifest)
        assert any("경로" in v for v in violations)

    def test_manifest_with_cookie_not_safe(self):
        manifest = build_manifest(TASK_ID, [], task_downloaded_filenames=[])
        manifest["cookie"] = "abc"
        assert is_safe_manifest(manifest) is False


class TestServerUploadPolicy:
    def _make_manifest(self, files_info):
        return build_manifest(
            TASK_ID,
            files_info,
            task_downloaded_filenames=[f["filename"] for f in files_info],
        )

    def test_pdf_passes_server_validation(self):
        manifest = self._make_manifest([{"filename": "notice.pdf", "size_bytes": 1024}])
        result = validate_upload_manifest(manifest)
        assert len(result["safe_files"]) == 1

    def test_pfx_blocked_at_server(self):
        manifest = self._make_manifest([{"filename": "cert.pfx", "size_bytes": 512}])
        result = validate_upload_manifest(manifest)
        assert len(result["safe_files"]) == 0

    def test_cert_detected_manifest_blocked_at_server(self):
        manifest = self._make_manifest([{"filename": "cert.pfx", "size_bytes": 512}])
        assert manifest["certificate_file_detected"] is True
        result = validate_upload_manifest(manifest)
        assert len(result["violations"]) > 0

    def test_no_sensitive_data_received(self):
        manifest = self._make_manifest([{"filename": "notice.pdf", "size_bytes": 1024}])
        result = validate_upload_manifest(manifest)
        assert result["sensitive_data_received"] is False
        assert result["certificate_received"] is False

    def test_server_policy_summary(self):
        summary = get_server_upload_policy_summary()
        assert summary["server_downloads_from_external"] is False
        assert summary["server_receives_file_binary"] is False
        assert summary["server_receives_credentials"] is False
        assert summary["certificate_upload_allowed"] is False
        assert summary["npki_upload_allowed"] is False
        assert summary["executable_upload_allowed"] is False


class TestSmoke:
    def test_playwright_runner_import_ok(self):
        from core.agent_runtime.runtime.playwright import playwright_runner

        assert hasattr(playwright_runner, "run_task")

    def test_auth_wait_import_ok(self):
        from core.agent_runtime.runtime.auth.auth_wait_controller import enter_auth_wait

        assert callable(enter_auth_wait)

    def test_auto_resume_import_ok(self):
        from core.agent_runtime.runtime.auth.auto_resume_after_auth import can_auto_resume

        assert can_auto_resume("read_page") is True
        assert can_auto_resume("final_submit") is False

    def test_notification_adapter_import_ok(self):
        from core.agent_runtime.runtime.notify.user_notification_adapter import send_notification

        assert callable(send_notification)

    def test_browser_foreground_import_ok(self):
        from core.agent_runtime.runtime.playwright.browser_foreground_adapter import request_foreground

        result = request_foreground(is_headed=False)
        assert result["sensitive_data_read"] is False
