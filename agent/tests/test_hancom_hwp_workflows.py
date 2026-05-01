"""한컴 HWP→HWPX 워크플로우 통합 테스트 (mock 기반)."""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.hancom.hwp import workflows


class TestHWPWorkflows(unittest.TestCase):
    """HWP→HWPX 워크플로우 테스트."""

    def setUp(self):
        """테스트 준비."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def create_test_hwp(self) -> str:
        """테스트용 HWP 파일 생성."""
        hwp_path = os.path.join(self.temp_dir.name, "test.hwp")
        Path(hwp_path).touch()
        return hwp_path

    def create_test_hwpx(self) -> str:
        """테스트용 HWPX 파일 생성."""
        hwpx_path = os.path.join(self.temp_dir.name, "test.hwpx")

        with zipfile.ZipFile(hwpx_path, "w") as zf:
            zf.writestr("mimetype", "application/vnd.hancom.hwpx+zip")
            zf.writestr("Contents/content.hpf", b"")
            zf.writestr("Contents/1.hml", "<section></section>")
            zf.writestr("META-INF/manifest.xml", '<?xml version="1.0"?>')

        return hwpx_path

    @patch("agent.hancom.hwp.workflows.converter.convert_hwp_to_hwpx")
    @patch("agent.hancom.hwp.workflows.package_validator.validate_hwpx_package")
    @patch("agent.hancom.hwp.workflows.package_validator.get_hwpx_structure")
    def test_convert_hwp_to_hwpx_copy_success(self, mock_structure, mock_validate, mock_convert):
        """변환 성공."""
        input_path = self.create_test_hwp()
        output_path = os.path.join(self.temp_dir.name, "output.hwpx")

        # Mock 설정
        mock_convert.return_value = {
            "success": True,
            "input_path": input_path,
            "output_path": output_path,
            "output_size": 50000,
            "error": None,
        }
        mock_validate.return_value = (True, None)
        mock_structure.return_value = {
            "valid": True,
            "file_count": 10,
            "sections": ["Contents/1.hml"],
        }

        # 실제 출력 파일 생성
        self.create_test_hwpx()

        # 워크플로우 실행
        result = workflows.convert_hwp_to_hwpx_copy({
            "input_path": input_path,
            "output_path": output_path,
            "visible": False,
        })

        # 검증
        self.assertTrue(result["success"])
        self.assertEqual(result["input_path"], input_path)
        self.assertEqual(result["output_path"], output_path)
        self.assertEqual(result["output_size"], 50000)
        self.assertTrue(result["hwpx_valid"])
        self.assertEqual(result["hwpx_file_count"], 10)
        self.assertEqual(result["hwpx_sections"], 1)
        self.assertIsNone(result["error"])

    @patch("agent.hancom.hwp.workflows.converter.convert_hwp_to_hwpx")
    def test_convert_hwp_to_hwpx_copy_conversion_failed(self, mock_convert):
        """변환 실패."""
        input_path = self.create_test_hwp()
        output_path = os.path.join(self.temp_dir.name, "output.hwpx")

        # Mock: 변환 실패
        mock_convert.return_value = {
            "success": False,
            "error": "HANCOM_NOT_INSTALLED",
        }

        # 워크플로우 실행
        result = workflows.convert_hwp_to_hwpx_copy({
            "input_path": input_path,
            "output_path": output_path,
        })

        # 검증
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "HANCOM_NOT_INSTALLED")

    @patch("agent.hancom.hwp.workflows.converter.convert_hwp_to_hwpx")
    @patch("agent.hancom.hwp.workflows.package_validator.validate_hwpx_package")
    def test_convert_hwp_to_hwpx_copy_validation_failed(self, mock_validate, mock_convert):
        """HWPX 검증 실패."""
        input_path = self.create_test_hwp()
        output_path = os.path.join(self.temp_dir.name, "output.hwpx")

        # Mock 설정
        mock_convert.return_value = {
            "success": True,
            "input_path": input_path,
            "output_path": output_path,
            "output_size": 50000,
        }
        mock_validate.return_value = (False, "INVALID_ZIP_FORMAT")

        # 워크플로우 실행
        result = workflows.convert_hwp_to_hwpx_copy({
            "input_path": input_path,
            "output_path": output_path,
        })

        # 검증
        self.assertFalse(result["success"])
        self.assertFalse(result["hwpx_valid"])
        self.assertIn("INVALID_ZIP_FORMAT", result["error"])

    def test_convert_hwp_to_hwpx_copy_missing_paths(self):
        """필수 파라미터 누락."""
        result = workflows.convert_hwp_to_hwpx_copy({})

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "INPUT_OUTPUT_PATH_REQUIRED")


if __name__ == "__main__":
    unittest.main()
