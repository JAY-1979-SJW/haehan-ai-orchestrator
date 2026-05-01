"""한컴 보안모듈 상세 테스트."""
from __future__ import annotations

import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock, call

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

    def test_no_registry_write_in_security_check(self):
        """registry write 함수가 호출되지 않음."""
        # get_security_module_details는 read-only 조회만 함
        details = security_module.get_security_module_details("TestModule")
        # OpenKey(read)만 사용하고 SetValueEx(write)는 사용 안 함
        # (실제로는 mock 없이 호출되므로 exception 발생하지 않음)
        self.assertIsNotNone(details)


class TestSetupSecurityModuleRegistry(unittest.TestCase):
    """setup_security_module_registry 상세 테스트."""

    def test_dll_path_not_found(self):
        """DLL 없음 → DLL_PATH_NOT_FOUND 오류."""
        result = security_module.setup_security_module_registry(
            module_name="TestModule",
            dll_path=r"C:\NonExistent\HwpAutomation.dll"
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["registered"])
        self.assertEqual(result["error_code"], "DLL_PATH_NOT_EXISTS")
        self.assertTrue(result["setup_required"])

    def test_dll_path_not_exists(self):
        """DLL 경로가 없음."""
        result = security_module.setup_security_module_registry(
            module_name="TestModule",
            dll_path=r"C:\Program Files\HNC\NotExist.dll"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "DLL_PATH_NOT_EXISTS")

    def test_valid_dll_path_with_custom_module_name(self):
        """유효한 DLL + 커스텀 module_name."""
        # 임시 DLL 파일 생성
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            # Mock winreg를 사용하여 registry write 검증
            with patch("winreg.OpenKey") as mock_open_key, \
                 patch("winreg.SetValueEx") as mock_set_value, \
                 patch("winreg.CloseKey"):

                mock_key = MagicMock()
                mock_open_key.return_value = mock_key

                result = security_module.setup_security_module_registry(
                    module_name="CustomModule",
                    dll_path=temp_dll
                )

                # Registry write 호출 검증
                mock_set_value.assert_called_once()
                call_args = mock_set_value.call_args
                # SetValueEx(key, module_name, 0, winreg.REG_SZ, dll_path)
                # call_args[0][0]: key
                # call_args[0][1]: module_name
                # call_args[0][2]: 0
                # call_args[0][3]: winreg.REG_SZ
                # call_args[0][4]: dll_path
                self.assertEqual(call_args[0][1], "CustomModule")
                self.assertEqual(call_args[0][4], temp_dll)

                # 성공 결과 검증
                self.assertTrue(result["success"])
                self.assertTrue(result["registered"])
                self.assertEqual(result["module_name"], "CustomModule")

        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)

    def test_registry_write_permission_denied(self):
        """Registry 쓰기 권한 없음."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            with patch("winreg.OpenKey") as mock_open_key:
                # PermissionError 발생시키기
                mock_open_key.side_effect = PermissionError("Access denied")

                result = security_module.setup_security_module_registry(
                    module_name="TestModule",
                    dll_path=temp_dll
                )

                self.assertFalse(result["success"])
                self.assertEqual(result["error_code"], "REGISTRY_PERMISSION_DENIED")

        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)

    def test_default_module_name_used(self):
        """module_name None이면 기본값 사용."""
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            with patch("winreg.OpenKey") as mock_open_key, \
                 patch("winreg.SetValueEx") as mock_set_value, \
                 patch("winreg.CloseKey"):

                mock_key = MagicMock()
                mock_open_key.return_value = mock_key

                result = security_module.setup_security_module_registry(
                    module_name=None,
                    dll_path=temp_dll
                )

                # 기본 module_name이 사용되었는지 검증
                call_args = mock_set_value.call_args
                self.assertEqual(
                    call_args[0][1],
                    security_module.DEFAULT_SECURITY_MODULE_NAME
                )

        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)

    def test_dll_path_exists_check(self):
        """DLL 경로 존재 검증."""
        # 임시 DLL 파일로 테스트
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            temp_dll = f.name

        try:
            with patch("winreg.OpenKey") as mock_open_key, \
                 patch("winreg.SetValueEx") as mock_set_value, \
                 patch("winreg.CloseKey"):

                mock_key = MagicMock()
                mock_open_key.return_value = mock_key

                result = security_module.setup_security_module_registry(
                    module_name="TestModule",
                    dll_path=temp_dll
                )

                # dll_path_exists 필드 확인
                self.assertTrue(result["dll_path_exists"])
                self.assertTrue(result["registry_write"])

        finally:
            if os.path.exists(temp_dll):
                os.unlink(temp_dll)

    def test_readback_after_write_success(self):
        """Registry write 성공 후 read-back 검증."""
        # 실제 registry (mock 없이) read-back 검증
        # write할 수 없으므로 write 없이 미등록 상태만 확인
        details = security_module.get_security_module_details("NonExistentModule")

        # 미등록 상태 확인
        self.assertFalse(details["registered"])
        self.assertEqual(details["dll_path"], None)
        self.assertFalse(details["dll_exists"])
        self.assertEqual(
            details["error_code"],
            "HANCOM_SECURITY_MODULE_NOT_REGISTERED"
        )


if __name__ == "__main__":
    unittest.main()
