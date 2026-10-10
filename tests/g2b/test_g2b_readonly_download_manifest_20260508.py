"""
나라장터 read-only 다운로드 manifest 테스트
"""

from ai_orchestrator.agent_hub.policy.file_upload_policy import validate_upload_manifest
from core.agent_runtime.runtime.download.download_policy import check_file
from core.agent_runtime.runtime.download.download_upload_manifest import (
    build_manifest,
    is_safe_manifest,
)

TASK_ID = "g2b-manifest-test-001"

# 나라장터 실제 첨부 파일 유형 시나리오
_G2B_TYPICAL_FILES = [
    {"filename": "입찰공고문.pdf", "size_bytes": 51200},
    {"filename": "첨부서류_1.hwpx", "size_bytes": 20480},
    {"filename": "설계도면.xlsx", "size_bytes": 30720},
    {"filename": "공사내역서.csv", "size_bytes": 10240},
]

_G2B_DANGEROUS_FILES = [
    {"filename": "인증서.pfx", "size_bytes": 4096},
    {"filename": "setup.exe", "size_bytes": 1024000},
    {"filename": "signCert.der", "size_bytes": 2048, "file_path": "C:/NPKI/signCert.der"},
    {"filename": "my_password.pdf", "size_bytes": 1024},
]


class TestG2bDownloadManifest:
    def test_typical_g2b_pdf_allowed(self):
        result = check_file("입찰공고문.pdf", task_downloaded_files=["입찰공고문.pdf"])
        assert result["upload_allowed"] is True

    def test_typical_g2b_hwpx_allowed(self):
        result = check_file("첨부서류.hwpx", task_downloaded_files=["첨부서류.hwpx"])
        assert result["upload_allowed"] is True

    def test_typical_g2b_xlsx_allowed(self):
        result = check_file("설계도면.xlsx", task_downloaded_files=["설계도면.xlsx"])
        assert result["upload_allowed"] is True

    def test_cert_pfx_blocked(self):
        result = check_file("인증서.pfx", task_downloaded_files=["인증서.pfx"])
        assert result["upload_allowed"] is False
        assert result["certificate_file_detected"] is True

    def test_npki_path_blocked(self):
        result = check_file("signCert.der", file_path="C:/NPKI/signCert.der", task_downloaded_files=["signCert.der"])
        assert result["upload_allowed"] is False
        assert "NPKI" in result["blocked_reason"]

    def test_exe_blocked(self):
        result = check_file("setup.exe", task_downloaded_files=["setup.exe"])
        assert result["upload_allowed"] is False

    def test_password_filename_blocked(self):
        result = check_file("my_password.pdf", task_downloaded_files=["my_password.pdf"])
        assert result["upload_allowed"] is False

    def test_manifest_from_typical_g2b_files(self):
        filenames = [f["filename"] for f in _G2B_TYPICAL_FILES]
        manifest = build_manifest(TASK_ID, _G2B_TYPICAL_FILES, task_downloaded_filenames=filenames)
        assert manifest["allowed_count"] == len(_G2B_TYPICAL_FILES)
        assert manifest["blocked_count"] == 0
        assert manifest["certificate_file_detected"] is False
        assert manifest["sensitive_data_detected"] is False

    def test_manifest_from_dangerous_files_all_blocked(self):
        filenames = [f["filename"] for f in _G2B_DANGEROUS_FILES]
        manifest = build_manifest(TASK_ID, _G2B_DANGEROUS_FILES, task_downloaded_filenames=filenames)
        assert manifest["blocked_count"] == len(_G2B_DANGEROUS_FILES)
        assert manifest["allowed_count"] == 0

    def test_manifest_cert_detected_flag(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "cert.pfx", "size_bytes": 512}],
            task_downloaded_filenames=["cert.pfx"],
        )
        assert manifest["certificate_file_detected"] is True

    def test_manifest_no_local_path_exported(self):
        files = [
            {"filename": "입찰공고문.pdf", "size_bytes": 51200, "file_path": "C:/Users/secret/Downloads/입찰공고문.pdf"}
        ]
        manifest = build_manifest(TASK_ID, files, task_downloaded_filenames=["입찰공고문.pdf"])
        for entry in manifest["files"]:
            assert "file_path" not in entry
            assert "local_path" not in entry
            assert "absolute_path" not in entry

    def test_manifest_no_cookie_session_password(self):
        manifest = build_manifest(
            TASK_ID, _G2B_TYPICAL_FILES, task_downloaded_filenames=[f["filename"] for f in _G2B_TYPICAL_FILES]
        )
        assert "cookie" not in manifest or manifest.get("cookie") in (None, False, "")
        assert "session" not in manifest or manifest.get("session") in (None, False, "")
        assert "password" not in manifest or manifest.get("password") in (None, False, "")
        assert "otp" not in manifest or manifest.get("otp") in (None, False, "")

    def test_manifest_safe_for_export(self):
        manifest = build_manifest(
            TASK_ID, _G2B_TYPICAL_FILES, task_downloaded_filenames=[f["filename"] for f in _G2B_TYPICAL_FILES]
        )
        assert is_safe_manifest(manifest) is True

    def test_server_validates_manifest_clean(self):
        filenames = [f["filename"] for f in _G2B_TYPICAL_FILES]
        manifest = build_manifest(TASK_ID, _G2B_TYPICAL_FILES, task_downloaded_filenames=filenames)
        result = validate_upload_manifest(manifest)
        assert result["sensitive_data_received"] is False
        assert result["certificate_received"] is False
        assert len(result["safe_files"]) == len(_G2B_TYPICAL_FILES)

    def test_server_rejects_manifest_with_cert(self):
        manifest = build_manifest(
            TASK_ID,
            [{"filename": "cert.pfx", "size_bytes": 512}],
            task_downloaded_filenames=["cert.pfx"],
        )
        result = validate_upload_manifest(manifest)
        assert len(result["violations"]) > 0
        assert len(result["safe_files"]) == 0

    def test_mixed_manifest_server_result(self):
        all_files = _G2B_TYPICAL_FILES + [{"filename": "cert.pfx", "size_bytes": 512}]  # noqa: RUF005
        filenames = [f["filename"] for f in all_files]
        manifest = build_manifest(TASK_ID, all_files, task_downloaded_filenames=filenames)
        result = validate_upload_manifest(manifest)
        # cert 탐지로 전체 거부
        assert len(result["violations"]) > 0
