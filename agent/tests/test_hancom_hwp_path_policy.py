"""한컴 경로 검증 단위 테스트."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent.hancom.hwp import path_policy


class TestPathPolicy(unittest.TestCase):
    """경로 검증 정책 테스트."""

    def test_validate_input_hwp_path_success(self):
        """유효한 HWP 경로 검증."""
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as f:
            temp_path = f.name

        try:
            valid, error = path_policy.validate_input_hwp_path(temp_path)
            self.assertTrue(valid)
            self.assertIsNone(error)
        finally:
            os.remove(temp_path)

    def test_validate_input_hwp_path_not_found(self):
        """존재하지 않는 HWP 파일."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = os.path.join(tmpdir, "nonexistent.hwp")
            valid, error = path_policy.validate_input_hwp_path(nonexistent)
            self.assertFalse(valid)
            self.assertEqual(error, "INPUT_FILE_NOT_FOUND")

    def test_validate_input_hwp_path_wrong_extension(self):
        """잘못된 확장자."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            valid, error = path_policy.validate_input_hwp_path(temp_path)
            self.assertFalse(valid)
            self.assertEqual(error, "INPUT_NOT_HWP_FILE")
        finally:
            os.remove(temp_path)

    def test_validate_input_hwp_path_relative(self):
        """상대 경로."""
        valid, error = path_policy.validate_input_hwp_path("./file.hwp")
        self.assertFalse(valid)
        self.assertEqual(error, "ABSOLUTE_PATH_REQUIRED")

    def test_validate_output_hwpx_path_success(self):
        """유효한 HWPX 출력 경로."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.hwpx")
            valid, error = path_policy.validate_output_hwpx_path(output_path)
            self.assertTrue(valid)
            self.assertIsNone(error)

    def test_validate_output_hwpx_path_wrong_extension(self):
        """잘못된 확장자 (.hwp instead of .hwpx)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output.hwp")
            valid, error = path_policy.validate_output_hwpx_path(output_path)
            self.assertFalse(valid)
            self.assertEqual(error, "OUTPUT_MUST_BE_HWPX")

    def test_check_original_overwrite_same_path(self):
        """원본 덮어쓰기 방지 (같은 경로)."""
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as f:
            temp_path = f.name

        try:
            safe, error = path_policy.check_original_overwrite(temp_path, temp_path)
            self.assertFalse(safe)
            self.assertEqual(error, "OUTPUT_SAME_AS_INPUT")
        finally:
            os.remove(temp_path)

    def test_check_original_overwrite_different_path(self):
        """다른 경로 (안전함)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.hwp")
            output_path = os.path.join(tmpdir, "output.hwpx")

            # 입력 파일 생성
            Path(input_path).touch()

            safe, error = path_policy.check_original_overwrite(input_path, output_path)
            self.assertTrue(safe)
            self.assertIsNone(error)

    def test_validate_conversion_paths_success(self):
        """전체 경로 검증 성공."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "input.hwp")
            output_path = os.path.join(tmpdir, "output.hwpx")

            # 입력 파일 생성
            Path(input_path).touch()

            valid, error = path_policy.validate_conversion_paths(input_path, output_path)
            self.assertTrue(valid)
            self.assertIsNone(error)

    def test_validate_conversion_paths_missing_input(self):
        """입력 파일 없음."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "missing.hwp")
            output_path = os.path.join(tmpdir, "output.hwpx")

            valid, error = path_policy.validate_conversion_paths(input_path, output_path)
            self.assertFalse(valid)
            self.assertEqual(error, "INPUT_FILE_NOT_FOUND")

    def test_get_path_info(self):
        """경로 정보 조회."""
        with tempfile.NamedTemporaryFile(suffix=".hwp", delete=False) as f:
            temp_path = f.name

        try:
            info = path_policy.get_path_info(temp_path)
            self.assertTrue(info["exists"])
            self.assertTrue(info["is_readable"])
            self.assertEqual(info["extension"], ".hwp")
            self.assertIsNotNone(info["size"])
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
