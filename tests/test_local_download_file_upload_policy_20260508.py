"""
download_policy 테스트
"""

from core.agent_runtime.runtime.download.download_policy import (
    MAX_FILE_SIZE_BYTES,
    check_file,
    check_files,
)

TASK_FILES = ["notice.pdf", "attachment_1.hwpx", "data.xlsx", "report.csv"]


class TestAllowedExtensions:
    def test_pdf_allowed(self):
        result = check_file("notice.pdf", task_downloaded_files=TASK_FILES)
        assert result["upload_allowed"] is True
        assert result["blocked_reason"] is None

    def test_hwpx_allowed(self):
        result = check_file("attachment_1.hwpx", task_downloaded_files=TASK_FILES)
        assert result["upload_allowed"] is True

    def test_xlsx_allowed(self):
        result = check_file("data.xlsx", task_downloaded_files=TASK_FILES)
        assert result["upload_allowed"] is True

    def test_csv_allowed(self):
        result = check_file("report.csv", task_downloaded_files=TASK_FILES)
        assert result["upload_allowed"] is True

    def test_xls_allowed(self):
        result = check_file("data.xls", task_downloaded_files=["data.xls"])
        assert result["upload_allowed"] is True

    def test_docx_allowed(self):
        result = check_file("doc.docx", task_downloaded_files=["doc.docx"])
        assert result["upload_allowed"] is True

    def test_zip_allowed(self):
        result = check_file("files.zip", task_downloaded_files=["files.zip"])
        assert result["upload_allowed"] is True

    def test_txt_allowed(self):
        result = check_file("readme.txt", task_downloaded_files=["readme.txt"])
        assert result["upload_allowed"] is True

    def test_png_allowed(self):
        result = check_file("screenshot.png", task_downloaded_files=["screenshot.png"])
        assert result["upload_allowed"] is True

    def test_jpg_allowed(self):
        result = check_file("image.jpg", task_downloaded_files=["image.jpg"])
        assert result["upload_allowed"] is True


class TestBlockedExtensions:
    def test_exe_blocked(self):
        result = check_file("setup.exe", task_downloaded_files=["setup.exe"])
        assert result["upload_allowed"] is False
        assert "차단" in result["blocked_reason"]

    def test_pfx_blocked(self):
        result = check_file("cert.pfx", task_downloaded_files=["cert.pfx"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_p12_blocked(self):
        result = check_file("cert.p12", task_downloaded_files=["cert.p12"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_key_blocked(self):
        result = check_file("private.key", task_downloaded_files=["private.key"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_pem_blocked(self):
        result = check_file("cert.pem", task_downloaded_files=["cert.pem"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_cer_blocked(self):
        result = check_file("cert.cer", task_downloaded_files=["cert.cer"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_der_blocked(self):
        result = check_file("cert.der", task_downloaded_files=["cert.der"])
        assert result["upload_allowed"] is False

    def test_msi_blocked(self):
        result = check_file("install.msi", task_downloaded_files=["install.msi"])
        assert result["upload_allowed"] is False

    def test_bat_blocked(self):
        result = check_file("run.bat", task_downloaded_files=["run.bat"])
        assert result["upload_allowed"] is False

    def test_ps1_blocked(self):
        result = check_file("script.ps1", task_downloaded_files=["script.ps1"])
        assert result["upload_allowed"] is False


class TestNpkiPath:
    def test_npki_path_blocked(self):
        result = check_file(
            "signCert.der",
            file_path="C:/Users/user/AppData/LocalLow/NPKI/signCert.der",
            task_downloaded_files=["signCert.der"],
        )
        assert result["upload_allowed"] is False
        assert "NPKI" in result["blocked_reason"]

    def test_npki_lowercase_path_blocked(self):
        result = check_file(
            "cert.cer",
            file_path="/home/user/.npki/cert.cer",
            task_downloaded_files=["cert.cer"],
        )
        assert result["upload_allowed"] is False

    def test_usercert_path_blocked(self):
        result = check_file(
            "usercert.der",
            file_path="C:/Users/user/usercert/usercert.der",
            task_downloaded_files=["usercert.der"],
        )
        assert result["upload_allowed"] is False

    def test_normal_path_not_blocked(self):
        result = check_file(
            "notice.pdf",
            file_path="C:/Users/user/Downloads/notice.pdf",
            task_downloaded_files=["notice.pdf"],
        )
        assert result["upload_allowed"] is True


class TestSensitiveFilename:
    def test_password_in_name_blocked(self):
        result = check_file("my_password.pdf", task_downloaded_files=["my_password.pdf"])
        assert result["upload_allowed"] is False
        assert "password" in result["blocked_reason"]

    def test_secret_in_name_blocked(self):
        result = check_file("secret_doc.xlsx", task_downloaded_files=["secret_doc.xlsx"])
        assert result["upload_allowed"] is False

    def test_token_in_name_blocked(self):
        result = check_file("token_data.csv", task_downloaded_files=["token_data.csv"])
        assert result["upload_allowed"] is False

    def test_session_in_name_blocked(self):
        result = check_file("session_log.txt", task_downloaded_files=["session_log.txt"])
        assert result["upload_allowed"] is False

    def test_cookie_in_name_blocked(self):
        result = check_file("cookie_backup.zip", task_downloaded_files=["cookie_backup.zip"])
        assert result["upload_allowed"] is False

    def test_otp_in_name_blocked(self):
        result = check_file("otp_codes.txt", task_downloaded_files=["otp_codes.txt"])
        assert result["upload_allowed"] is False

    def test_normal_name_not_blocked(self):
        result = check_file("입찰공고문.pdf", task_downloaded_files=["입찰공고문.pdf"])
        assert result["upload_allowed"] is True


class TestTaskBoundary:
    def test_task_external_file_blocked(self):
        result = check_file(
            "unrelated.pdf",
            task_downloaded_files=["notice.pdf", "attachment.hwpx"],
        )
        assert result["upload_allowed"] is False
        assert "task 외부" in result["blocked_reason"]

    def test_task_file_allowed(self):
        result = check_file(
            "notice.pdf",
            task_downloaded_files=["notice.pdf", "attachment.hwpx"],
        )
        assert result["upload_allowed"] is True

    def test_no_task_filter_passes(self):
        result = check_file("notice.pdf", task_downloaded_files=None)
        assert result["upload_allowed"] is True


class TestFileSizeLimit:
    def test_oversized_file_blocked(self):
        result = check_file(
            "bigfile.pdf",
            size_bytes=MAX_FILE_SIZE_BYTES + 1,
            task_downloaded_files=["bigfile.pdf"],
        )
        assert result["upload_allowed"] is False
        assert "크기 초과" in result["blocked_reason"]

    def test_exact_limit_allowed(self):
        result = check_file(
            "file.pdf",
            size_bytes=MAX_FILE_SIZE_BYTES,
            task_downloaded_files=["file.pdf"],
        )
        assert result["upload_allowed"] is True

    def test_small_file_allowed(self):
        result = check_file(
            "notice.pdf",
            size_bytes=1024,
            task_downloaded_files=["notice.pdf"],
        )
        assert result["upload_allowed"] is True


class TestSafeFields:
    def test_no_sensitive_data_detected(self):
        result = check_file("notice.pdf", task_downloaded_files=["notice.pdf"])
        assert result["sensitive_data_detected"] is False

    def test_safe_name_no_path(self):
        result = check_file(
            "notice.pdf",
            file_path="C:/Users/user/Downloads/notice.pdf",
            task_downloaded_files=["notice.pdf"],
        )
        assert "/" not in result["safe_name"]
        assert "\\" not in result["safe_name"]

    def test_extension_lowercase(self):
        result = check_file("FILE.PDF", task_downloaded_files=["FILE.PDF"])
        assert result["extension"] == ".pdf"


class TestCheckFiles:
    def test_multiple_files(self):
        files = [
            {"filename": "notice.pdf", "size_bytes": 1024},
            {"filename": "cert.pfx", "size_bytes": 2048},
        ]
        results = check_files(files, task_downloaded_files=["notice.pdf", "cert.pfx"])
        assert results[0]["upload_allowed"] is True
        assert results[1]["upload_allowed"] is False
