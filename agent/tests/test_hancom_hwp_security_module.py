"""한컴 보안모듈 단위 테스트."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from agent.hancom.hwp import security_module


class TestSecurityModule(unittest.TestCase):
    """보안모듈 테스트."""

    def test_get_security_module_status_registered(self):
        """보안모듈 등록됨."""
        with patch.object(
            security_module,
            "check_security_module_registered",
            return_value=(True, None),
        ):
            status = security_module.get_security_module_status()

            self.assertTrue(status["registered"])
            self.assertEqual(status["module_type"], "hancom_official")
            self.assertIsNone(status["error"])

    def test_get_security_module_status_not_registered(self):
        """보안모듈 미등록."""
        with patch.object(
            security_module,
            "check_security_module_registered",
            return_value=(False, "MODULE_NOT_REGISTERED"),
        ):
            status = security_module.get_security_module_status()

            self.assertFalse(status["registered"])
            self.assertIsNone(status["module_type"])
            self.assertEqual(status["error"], "MODULE_NOT_REGISTERED")

    def test_get_security_module_status_check_failed(self):
        """보안모듈 확인 실패."""
        with patch.object(
            security_module,
            "check_security_module_registered",
            return_value=(False, "MODULE_CHECK_FAILED"),
        ):
            status = security_module.get_security_module_status()

            self.assertFalse(status["registered"])
            self.assertIsNone(status["module_type"])
            self.assertEqual(status["error"], "MODULE_CHECK_FAILED")


if __name__ == "__main__":
    unittest.main()
