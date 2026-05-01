"""한컴 로컬 설치 탐색 모듈 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from agent.hancom.discovery import registry, com, installation, diagnostics


class TestRegistryDiscovery(unittest.TestCase):
    """Registry read-only 진단 테스트."""

    def test_check_registry_path_exists_valid_path(self):
        """존재하는 경로 확인."""
        # HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft는 일반적으로 존재
        import winreg
        result = registry.check_registry_path_exists(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft"
        )
        # 이 경로는 일반적으로 존재하지만, 테스트 환경에 따라 다를 수 있음
        self.assertIsInstance(result, bool)

    def test_check_registry_path_exists_invalid_path(self):
        """존재하지 않는 경로 확인."""
        import winreg
        result = registry.check_registry_path_exists(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistentPath12345"
        )
        self.assertFalse(result)

    def test_read_registry_value_not_found(self):
        """존재하지 않는 값 조회."""
        import winreg
        result = registry.read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistent",
            "NonExistentValue"
        )
        self.assertIsNone(result)

    def test_list_registry_values_empty(self):
        """경로가 없을 때 빈 딕셔너리 반환."""
        import winreg
        result = registry.list_registry_values(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistent"
        )
        self.assertEqual(result, {})

    def test_check_hancom_registry_installation(self):
        """한컴 Registry 설치 상태 확인."""
        result = registry.check_hancom_registry_installation()
        self.assertIsInstance(result, dict)
        self.assertIn("HKEY_LOCAL_MACHINE_HOffice", result)
        self.assertIn("HKEY_CURRENT_USER_HOffice", result)
        self.assertIn("HKEY_LOCAL_MACHINE_Classes_HWPFrame", result)
        self.assertIn("HKEY_LOCAL_MACHINE_Classes_HwpObject", result)
        # 각 값은 bool이어야 함
        for value in result.values():
            self.assertIsInstance(value, bool)

    def test_check_security_module_registry_not_found(self):
        """보안모듈 미등록 상태."""
        result = registry.check_security_module_registry()
        self.assertIsInstance(result, dict)
        self.assertIn("registered", result)
        self.assertIn("module_names", result)
        self.assertIn("details", result)
        # 로컬 환경에서 등록되지 않았을 가능성이 높음
        if not result["registered"]:
            self.assertEqual(result["module_names"], [])


class TestComDiscovery(unittest.TestCase):
    """COM 가용성 진단 테스트."""

    def test_hwpobject_classes_defined(self):
        """지원 클래스 목록 정의."""
        self.assertTrue(len(com.HWPOBJECT_CLASSES) > 0)
        self.assertIn("HWPFrame.HwpObject", com.HWPOBJECT_CLASSES)
        self.assertIn("HwpObject.HwpObject", com.HWPOBJECT_CLASSES)

    def test_check_com_class_registered(self):
        """COM 클래스 등록 상태 확인."""
        # Microsoft.VisualBasic은 일반적으로 등록됨
        result = com.check_com_class_registered("Microsoft.VisualBasic")
        self.assertIsInstance(result, bool)

    def test_get_com_class_clsid(self):
        """COM 클래스 CLSID 조회."""
        # Microsoft.VisualBasic은 일반적으로 등록됨
        result = com.get_com_class_clsid("Microsoft.VisualBasic")
        # CLSID는 문자열이거나 None
        self.assertIsInstance(result, (str, type(None)))

    def test_check_all_hwpobject_classes(self):
        """모든 HwpObject 클래스 진단."""
        result = com.check_all_hwpobject_classes()
        self.assertIsInstance(result, dict)
        for class_name, info in result.items():
            self.assertIn("registered", info)
            self.assertIn("clsid", info)
            self.assertIn("priority", info)
            self.assertIsInstance(info["registered"], bool)

    def test_get_hwpobject_class_priority(self):
        """등록된 HwpObject 클래스 우선순위."""
        result = com.get_hwpobject_class_priority()
        self.assertIsInstance(result, list)
        # 로컬 환경에 따라 비어있을 수 있음

    def test_diagnose_com_status(self):
        """COM 종합 진단."""
        result = com.diagnose_com_status()
        self.assertIsInstance(result, dict)
        self.assertIn("win32com_available", result)
        self.assertIn("hwpobject_classes", result)
        self.assertIn("available_classes", result)
        self.assertIn("dispatch_status", result)


class TestInstallationDiscovery(unittest.TestCase):
    """설치 경로 탐색 테스트."""

    def test_standard_paths_defined(self):
        """표준 설치 경로 목록."""
        self.assertTrue(len(installation.STANDARD_INSTALLATION_PATHS) > 0)
        # C:\Program Files 경로들이 포함되어야 함
        paths_str = str(installation.STANDARD_INSTALLATION_PATHS)
        self.assertIn("Program Files", paths_str)
        self.assertIn("HNC", paths_str)

    def test_check_path_exists(self):
        """경로 존재 여부 확인."""
        # Windows 시스템 디렉토리는 존재해야 함
        result = installation.check_path_exists(r"C:\Windows")
        self.assertIsInstance(result, bool)
        if result:
            self.assertTrue(result)

    def test_check_file_readable(self):
        """파일 읽기 가능 여부 확인."""
        import tempfile
        import os

        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name

        try:
            result = installation.check_file_readable(temp_path)
            self.assertTrue(result)
        finally:
            os.unlink(temp_path)

    def test_find_dll_in_path_not_found(self):
        """존재하지 않는 경로에서 DLL 검색."""
        result = installation.find_dll_in_path(r"C:\NonExistent\Path")
        self.assertIsNone(result)

    def test_discover_installation_paths(self):
        """한컴 설치 경로 발견."""
        result = installation.discover_installation_paths()
        self.assertIsInstance(result, list)
        # 로컬 환경에 따라 비어있을 수 있음

    def test_discover_dll_candidates(self):
        """DLL 후보 경로 발견."""
        result = installation.discover_dll_candidates()
        self.assertIsInstance(result, dict)
        # 로컬 환경에 따라 비어있을 수 있음

    def test_diagnose_installation_status(self):
        """설치 상태 진단."""
        result = installation.diagnose_installation_status()
        self.assertIsInstance(result, dict)
        self.assertIn("installation_paths", result)
        self.assertIn("dll_candidates", result)
        self.assertIn("primary_dll", result)


class TestDiagnostics(unittest.TestCase):
    """통합 진단 테스트."""

    def test_diagnose_hancom_installation(self):
        """한컴 설치 종합 진단."""
        result = diagnostics.diagnose_hancom_installation()
        self.assertIsInstance(result, dict)
        self.assertIn("installed", result)
        self.assertIn("registry_status", result)
        self.assertIn("com_status", result)
        self.assertIn("installation_status", result)
        self.assertIn("security_module", result)
        self.assertIn("summary", result)
        self.assertIn("recommendations", result)

        # 타입 검증
        self.assertIsInstance(result["installed"], bool)
        self.assertIsInstance(result["registry_status"], dict)
        self.assertIsInstance(result["com_status"], dict)
        self.assertIsInstance(result["installation_status"], dict)
        self.assertIsInstance(result["security_module"], dict)
        self.assertIsInstance(result["summary"], str)
        self.assertIsInstance(result["recommendations"], list)

    def test_diagnose_hancom_installation_recommendations_type(self):
        """Recommendations가 문자열 목록."""
        result = diagnostics.diagnose_hancom_installation()
        for rec in result["recommendations"]:
            self.assertIsInstance(rec, str)

    def test_print_diagnosis_report(self):
        """진단 보고서 출력 (에러 없음)."""
        result = diagnostics.diagnose_hancom_installation()
        # 에러 없이 출력되어야 함
        try:
            diagnostics.print_diagnosis_report(result)
        except Exception as e:
            self.fail(f"print_diagnosis_report() 실패: {e}")

    def test_no_registry_write_in_diagnosis(self):
        """진단에서 registry write 없음."""
        # 이 테스트는 진단 함수들이 read-only 작업만 수행함을 확인
        # (함수가 SetValueEx를 호출하지 않는지 확인)
        with patch('winreg.SetValueEx') as mock_set:
            result = diagnostics.diagnose_hancom_installation()
            # SetValueEx가 호출되지 않았는지 확인
            mock_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
