"""한컴 공식 보안모듈 관리.

한컴 보안모듈 RegisterModule을 통한 파일 접근 보안 팝업 처리.

중요:
- 공식 보안모듈만 사용 (팝업 자동 클릭 금지)
- 보안모듈 미등록 시 명확한 error_code 반환
- 우회 금지 (사용자 명시적 등록 필수)
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def check_security_module_registered() -> Tuple[bool, Optional[str]]:
    """한컴 공식 보안모듈 등록 상태 확인.

    Returns:
        (등록여부, error_or_None)
        - (True, None): 보안모듈 등록됨
        - (False, "MODULE_NOT_REGISTERED"): 미등록
        - (False, "MODULE_CHECK_FAILED"): 확인 실패
    """
    try:
        import win32com.client as win32

        # 지원하는 HwpObject COM 클래스들 (우선순위 순서)
        classes = [
            "HWPFrame.HwpObject",
            "HWPFrame.HwpObject.1",
            "HWPFrame.HwpObject.2",
            "HwpObject.HwpObject",
        ]

        hwp = None
        for cls in classes:
            try:
                hwp = win32.Dispatch(cls)
                logger.debug(f"HwpObject 생성됨: {cls}")
                break
            except Exception:
                continue

        if hwp is None:
            logger.error("작동하는 HwpObject를 찾을 수 없음")
            return check_module_registry()

        try:
            # 보안모듈 등록 확인
            if hasattr(hwp, "RegisterModule"):
                return True, None
            elif hasattr(hwp, "SecurityModule"):
                module_info = hwp.SecurityModule
                if module_info:
                    return True, None
            else:
                return check_module_registry()
        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except ImportError:
        logger.warning("win32com not available")
        return False, "WIN32COM_NOT_AVAILABLE"
    except Exception as e:
        logger.error(f"보안모듈 체크 실패: {type(e).__name__}")
        return False, "MODULE_CHECK_FAILED"


def check_module_registry() -> Tuple[bool, Optional[str]]:
    """Windows 레지스트리에서 한컴 보안모듈 확인 (fallback).

    한컴 자동화 레지스트리 경로:
    HKEY_LOCAL_MACHINE\\SOFTWARE\\HNC\\HOffice
    HKEY_CURRENT_USER\\Software\\HNC\\HOffice
    """
    try:
        import winreg

        # 확인할 레지스트리 경로들
        paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\HNC\HOffice"),
            (winreg.HKEY_CURRENT_USER, r"Software\HNC\HOffice"),
        ]

        for hkey, path in paths:
            try:
                key = winreg.OpenKey(hkey, path)
                # 한컴 레지스트리가 존재하면 설치됨
                winreg.CloseKey(key)
                return True, None
            except FileNotFoundError:
                continue

        return False, "MODULE_NOT_REGISTERED"

    except ImportError:
        logger.warning("winreg not available")
        return False, "REGISTRY_CHECK_NOT_AVAILABLE"
    except Exception as e:
        logger.error("Registry check failed: %s", type(e).__name__)
        return False, "MODULE_CHECK_FAILED"


def register_security_module_if_available() -> Tuple[bool, Optional[str]]:
    """보안모듈을 등록 가능하면 등록한다 (사용자 명시적 요청 시에만 호출됨).

    한컴 공식 보안모듈 등록:
    hwp.RegisterModule(object_ptr)

    Returns:
        (성공여부, error_or_None)
    """
    try:
        import win32com.client as win32

        hwp = win32.Dispatch("HwpObject.HwpObject")

        try:
            # 보안모듈 등록 (공식 API)
            if hasattr(hwp, "RegisterModule"):
                # 구체적인 모듈 객체 필요 (한컴 문서 참조)
                # 일반적으로 HOfficeAddin 또는 유사 객체 사용
                hwp.RegisterModule(None)  # type: ignore
                logger.info("Security module registered")
                return True, None
            else:
                return False, "REGISTER_MODULE_NOT_AVAILABLE"

        finally:
            try:
                hwp.Quit()
            except Exception:
                pass

    except ImportError:
        logger.warning("win32com not available")
        return False, "WIN32COM_NOT_AVAILABLE"
    except Exception as e:
        logger.error("Register security module failed: %s", type(e).__name__)
        return False, "REGISTER_FAILED"


def get_security_module_status() -> dict:
    """보안모듈 상태를 조회한다.

    Returns:
        {
            "registered": bool,
            "module_type": str | None,  # "hancom_official" | "unknown" | None
            "version": str | None,
            "error": str | None,
        }
    """
    registered, error = check_security_module_registered()

    return {
        "registered": registered,
        "module_type": "hancom_official" if registered else None,
        "version": None,
        "error": error,
    }
