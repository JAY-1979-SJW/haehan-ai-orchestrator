"""한컴 보안모듈 상세 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from agent.hancom.hwp import security_module


class TestSecurityModuleDetailed(unittest.TestCase):
    """보안모듈 상세 검증 테스트."""

    def test_get_security_module_details_not_registered(self):
        """보안모듈 미등록 시 HANCOM_SECURITY_MODULE_NOT_REGISTERED 반환."""
        details = security_module.get_security_module_details("NonExistentModule")

        self.assertFalse(details["registered"])
        self.assertEqual(details["error_code"], "HANCOM_SECURITY_MODULE_NOT_REGISTERED")
        self.assertIsNone(details["dll_path"])
        self.assertFalse(details["dll_exists"])

    def test_get_security_module_details_uses_default_name(self):
        """기본 module_name 사용."""
        details = security_module.get_security_module_details()

        self.assertEqual(details["module_name"], security_module.DEFAULT_SECURITY_MODULE_NAME)

    def test_register_module_before_open_not_initialized(self):
        """HwpObject None이면 오류 반환."""
        success, error = security_module.register_module_before_open(None)

        self.assertFalse(success)
        self.assertEqual(error, "HWPOBJECT_NOT_INITIALIZED")

    def test_register_module_before_open_not_registered(self):
        """보안모듈 미등록이면 HANCOM_SECURITY_MODULE_NOT_REGISTERED 반환."""
        hwp = MagicMock()
        hwp.RegisterModule = MagicMock()

        success, error = security_module.register_module_before_open(
            hwp,
            module_name="NonExistentModule"
        )

        self.assertFalse(success)
        self.assertEqual(error, "HANCOM_SECURITY_MODULE_NOT_REGISTERED")
        # RegisterModule 호출 안 됨
        hwp.RegisterModule.assert_not_called()

    def test_register_module_before_open_success(self):
        """보안모듈 등록되었을 때 RegisterModule 호출."""
        hwp = MagicMock()
        hwp.RegisterModule = MagicMock(return_value=True)

        # registry에 module이 등록되어 있다고 가정
        with patch.object(
            security_module,
            "get_security_module_details",
            return_value={
                "registered": True,
                "module_name": "TestModule",
                "dll_path": r"C:\test\module.dll",
                "dll_exists": True,
                "registry_path": r"Software\HNC\HwpAutomation\Modules",
                "error_code": None,
            }
        ):
            success, error = security_module.register_module_before_open(
                hwp,
                module_name="TestModule"
            )

            self.assertTrue(success)
            self.assertIsNone(error)
            # RegisterModule이 호출되어야 함
            hwp.RegisterModule.assert_called_once_with("TestModule")

    def test_register_module_before_open_dll_not_exists(self):
        """DLL 경로가 없으면 등록 실패."""
        hwp = MagicMock()
        hwp.RegisterModule = MagicMock()

        # registry에 module이 있지만 DLL은 없다고 가정
        with patch.object(
            security_module,
            "get_security_module_details",
            return_value={
                "registered": True,
                "module_name": "TestModule",
                "dll_path": r"C:\nonexistent\module.dll",
                "dll_exists": False,
                "registry_path": r"Software\HNC\HwpAutomation\Modules",
                "error_code": "DLL_PATH_NOT_EXISTS",
            }
        ):
            success, error = security_module.register_module_before_open(
                hwp,
                module_name="TestModule"
            )

            self.assertFalse(success)
            self.assertEqual(error, "HANCOM_SECURITY_MODULE_NOT_REGISTERED")
            # RegisterModule 호출 안 됨
            hwp.RegisterModule.assert_not_called()

    def test_register_module_call_failure(self):
        """RegisterModule 호출 자체가 실패."""
        hwp = MagicMock()
        hwp.RegisterModule = MagicMock(side_effect=Exception("COM error"))

        with patch.object(
            security_module,
            "get_security_module_details",
            return_value={
                "registered": True,
                "module_name": "TestModule",
                "dll_path": r"C:\test\module.dll",
                "dll_exists": True,
                "registry_path": r"Software\HNC\HwpAutomation\Modules",
                "error_code": None,
            }
        ):
            success, error = security_module.register_module_before_open(
                hwp,
                module_name="TestModule"
            )

            self.assertFalse(success)
            self.assertEqual(error, "HANCOM_REGISTER_MODULE_FAILED")

    def test_security_module_registry_paths_defined(self):
        """registry 경로 목록이 정의되어 있음."""
        self.assertTrue(len(security_module.SECURITY_MODULE_REGISTRY_PATHS) >= 2)
        # HNC와 Hnc 경로 모두 포함
        paths = [p[0] for p in security_module.SECURITY_MODULE_REGISTRY_PATHS]
        self.assertTrue(any("HNC" in p for p in paths))
        self.assertTrue(any("Hnc" in p for p in paths))


if __name__ == "__main__":
    unittest.main()
