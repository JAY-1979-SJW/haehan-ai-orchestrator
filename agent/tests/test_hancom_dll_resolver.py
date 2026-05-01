"""한컴 DLL 경로 해석 모듈 테스트."""
from __future__ import annotations

import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock

from agent.hancom.discovery import dll_resolver


class TestDLLValidation(unittest.TestCase):
    """DLL 경로 검증 테스트."""

    def test_validate_dll_path_empty(self):
        """빈 경로 검증."""
        valid, error = dll_resolver.validate_dll_path("")
        self.assertFalse(valid)
        self.assertIsNotNone(error)

    def test_validate_dll_path_nonexistent(self):
        """존재하지 않는 파일."""
        valid, error = dll_resolver.validate_dll_path(r"C:\NonExistent\HwpAutomation.dll")
        self.assertFalse(valid)
        self.assertIn("찾을 수 없습니다", error)

    def test_validate_dll_path_directory(self):
        """디렉토리 (파일 아님)."""
        valid, error = dll_resolver.validate_dll_path(r"C:\Windows")
        self.assertFalse(valid)
        self.assertIn("파일이 아닙니다", error)

    def test_validate_dll_path_valid(self):
        """유효한 파일."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_path = f.name

        try:
            valid, error = dll_resolver.validate_dll_path(temp_path)
            self.assertTrue(valid)
            self.assertIsNone(error)
        finally:
            os.unlink(temp_path)

    def test_validate_dll_path_warning_different_name(self):
        """다른 이름의 DLL (경고 로깅)."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_path = f.name

        try:
            # 경로는 다른 이름이지만 유효함
            valid, error = dll_resolver.validate_dll_path(temp_path)
            self.assertTrue(valid)
            # 경고는 로깅되지만 검증 통과
        finally:
            os.unlink(temp_path)


class TestDLLResolution(unittest.TestCase):
    """DLL 경로 해석 테스트."""

    def test_resolve_dll_path_user_provided(self):
        """사용자 제공 경로 우선."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_path = f.name

        try:
            resolved, status = dll_resolver.resolve_dll_path(temp_path)
            self.assertEqual(resolved, temp_path)
            self.assertIn("사용자 지정", status)
        finally:
            os.unlink(temp_path)

    def test_resolve_dll_path_user_invalid(self):
        """사용자 경로가 유효하지 않음."""
        resolved, status = dll_resolver.resolve_dll_path(r"C:\NonExistent\HwpAutomation.dll")
        self.assertIsNone(resolved)
        self.assertIsNotNone(status)

    def test_resolve_dll_path_no_path(self):
        """경로 없을 때 (discovery 기반 또는 없음)."""
        resolved, status = dll_resolver.resolve_dll_path(None)
        # 로컬 환경에 따라 결과가 다를 수 있음
        self.assertIsInstance(resolved, (str, type(None)))
        self.assertIsNotNone(status)


class TestDLLCandidates(unittest.TestCase):
    """DLL 후보 경로 테스트."""

    def test_get_dll_candidates(self):
        """DLL 후보 조회."""
        candidates = dll_resolver.get_dll_candidates()
        self.assertIsInstance(candidates, dict)
        # 로컬 환경에 따라 결과가 다를 수 있음

    def test_dll_candidates_status_format(self):
        """DLL 후보 상태 포맷."""
        candidates = dll_resolver.get_dll_candidates()
        for dll_path, status in candidates.items():
            self.assertIsInstance(dll_path, str)
            self.assertIsInstance(status, str)
            self.assertIn(
                status,
                ["valid", "found_but_invalid", "valid_from_security_module"]
            )


class TestDLLResolverOutput(unittest.TestCase):
    """DLL 해석 정보 출력 테스트."""

    def test_print_dll_resolution_info(self):
        """출력 함수 에러 없음."""
        try:
            dll_resolver.print_dll_resolution_info(
                r"C:\Path\To\HwpAutomation.dll",
                "테스트 상태",
                {r"C:\Path\To\HwpAutomation.dll": "valid"}
            )
        except Exception as e:
            self.fail(f"print_dll_resolution_info() 실패: {e}")

    def test_print_dll_resolution_info_no_path(self):
        """경로 없을 때 출력."""
        try:
            dll_resolver.print_dll_resolution_info(
                None,
                "경로 없음",
                {}
            )
        except Exception as e:
            self.fail(f"print_dll_resolution_info() 실패: {e}")


if __name__ == "__main__":
    unittest.main()
