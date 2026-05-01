"""HWPX 패키지 검증 단위 테스트."""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from agent.hancom.hwpx import package_validator


class TestPackageValidator(unittest.TestCase):
    """HWPX 패키지 검증 테스트."""

    def create_valid_hwpx(self, temp_dir: str) -> str:
        """유효한 HWPX ZIP 파일 생성."""
        hwpx_path = os.path.join(temp_dir, "test.hwpx")

        with zipfile.ZipFile(hwpx_path, "w") as zf:
            # mimetype
            zf.writestr("mimetype", "application/vnd.hancom.hwpx+zip")

            # Contents 디렉토리
            zf.writestr("Contents/content.hpf", b"")
            zf.writestr("Contents/1.hml", "<section></section>")

            # META-INF
            zf.writestr("META-INF/manifest.xml", '<?xml version="1.0"?>')

        return hwpx_path

    def test_validate_hwpx_package_success(self):
        """유효한 HWPX 검증."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hwpx_path = self.create_valid_hwpx(tmpdir)

            valid, error = package_validator.validate_hwpx_package(hwpx_path)

            self.assertTrue(valid)
            self.assertIsNone(error)

    def test_validate_hwpx_package_not_found(self):
        """파일 없음."""
        valid, error = package_validator.validate_hwpx_package("/nonexistent/test.hwpx")

        self.assertFalse(valid)
        self.assertEqual(error, "HWPX_FILE_NOT_FOUND")

    def test_validate_hwpx_package_not_zip(self):
        """ZIP 파일 아님."""
        with tempfile.NamedTemporaryFile(suffix=".hwpx", delete=False) as f:
            f.write(b"not a zip file")
            temp_path = f.name

        try:
            valid, error = package_validator.validate_hwpx_package(temp_path)

            self.assertFalse(valid)
            self.assertEqual(error, "NOT_A_ZIP_FILE")
        finally:
            os.remove(temp_path)

    def test_validate_hwpx_package_no_contents(self):
        """Contents 디렉토리 없음."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hwpx_path = os.path.join(tmpdir, "test.hwpx")

            with zipfile.ZipFile(hwpx_path, "w") as zf:
                zf.writestr("other/file.txt", "content")

            valid, error = package_validator.validate_hwpx_package(hwpx_path)

            self.assertFalse(valid)
            self.assertEqual(error, "CONTENTS_DIR_NOT_FOUND")

    def test_validate_hwpx_package_no_sections(self):
        """섹션 파일 없음."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hwpx_path = os.path.join(tmpdir, "test.hwpx")

            with zipfile.ZipFile(hwpx_path, "w") as zf:
                zf.writestr("Contents/", "")

            valid, error = package_validator.validate_hwpx_package(hwpx_path)

            self.assertFalse(valid)
            self.assertEqual(error, "CONTENT_FILE_NOT_FOUND")

    def test_get_hwpx_structure(self):
        """HWPX 구조 분석."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hwpx_path = self.create_valid_hwpx(tmpdir)

            structure = package_validator.get_hwpx_structure(hwpx_path)

            self.assertTrue(structure["valid"])
            self.assertGreater(structure["file_count"], 0)
            self.assertIn("Contents", structure["directories"])
            self.assertTrue(structure["has_content_hpf"])
            self.assertGreater(len(structure["sections"]), 0)

    def test_extract_hwpx_metadata(self):
        """HWPX 메타데이터 추출."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hwpx_path = self.create_valid_hwpx(tmpdir)

            metadata = package_validator.extract_hwpx_metadata(hwpx_path)

            self.assertTrue(metadata["success"])
            self.assertGreater(metadata["file_count"], 0)
            self.assertGreater(metadata["total_size"], 0)
            self.assertGreaterEqual(metadata["content_size"], 0)


if __name__ == "__main__":
    unittest.main()
