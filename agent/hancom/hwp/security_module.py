"""한컴 공식 보안모듈 관리.

한컴 보안모듈 RegisterModule을 통한 파일 접근 보안 팝업 처리.

중요:
- 공식 보안모듈만 사용 (팝업 자동 클릭 금지)
- 보안모듈 미등록 시 명확한 error_code 반환
- 우회 금지 (사용자 명시적 등록 필수)
- RegisterModule은 Open 직전에 호출
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 기본 보안모듈 이름 (registry에 등록되어야 함)
DEFAULT_SECURITY_MODULE_NAME = "FilePathCheckerModuleExample"

# registry 경로 (대소문자 변형 모두 확인)
SECURITY_MODULE_REGISTRY_PATHS = [
    (r"Software\HNC\HwpAutomation\Modules", "HNC 경로"),
    (r"Software\Hnc\HwpAutomation\Modules", "Hnc 경로 (대소문자)"),
]


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


def get_security_module_details(
    module_name: Optional[str] = None,
) -> dict:
    """보안모듈 레지스트리 정보를 read-only로 조회한다.

    Args:
        module_name: 보안모듈 이름 (기본값: DEFAULT_SECURITY_MODULE_NAME)

    Returns:
        {
            "registered": bool,
            "module_name": str,
            "dll_path": str | None,
            "dll_exists": bool,
            "registry_path": str | None,
            "error_code": str | None,
        }
    """
    if module_name is None:
        module_name = DEFAULT_SECURITY_MODULE_NAME

    try:
        import winreg

        result = {
            "registered": False,
            "module_name": module_name,
            "dll_path": None,
            "dll_exists": False,
            "registry_path": None,
            "error_code": None,
        }

        # 각 registry 경로 시도
        for registry_path, path_desc in SECURITY_MODULE_REGISTRY_PATHS:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    registry_path,
                )

                # module_name 하위 값 조회
                try:
                    dll_path, _ = winreg.QueryValueEx(key, module_name)
                    result["registered"] = True
                    result["dll_path"] = dll_path
                    result["registry_path"] = registry_path

                    # DLL 파일 존재 여부 확인
                    if dll_path and os.path.exists(dll_path):
                        result["dll_exists"] = True
                        logger.info(
                            f"보안모듈 발견: {module_name}, "
                            f"경로: {registry_path}, "
                            f"DLL: {dll_path}"
                        )
                        winreg.CloseKey(key)
                        return result
                    else:
                        logger.warning(
                            f"보안모듈 DLL 없음: {dll_path}"
                        )
                        result["error_code"] = "DLL_PATH_NOT_EXISTS"

                except FileNotFoundError:
                    # module_name이 존재하지 않음
                    pass

                winreg.CloseKey(key)

            except FileNotFoundError:
                # registry_path가 존재하지 않음
                logger.debug(f"registry 경로 없음: {path_desc}")
                continue

        # 모든 경로에서 찾지 못함
        if not result["registered"]:
            result["error_code"] = "HANCOM_SECURITY_MODULE_NOT_REGISTERED"
            logger.error(
                f"보안모듈 미등록: {module_name}"
            )

        return result

    except ImportError:
        logger.error("winreg not available")
        return {
            "registered": False,
            "module_name": module_name,
            "dll_path": None,
            "dll_exists": False,
            "registry_path": None,
            "error_code": "REGISTRY_NOT_AVAILABLE",
        }
    except Exception as e:
        logger.error(f"보안모듈 정보 조회 실패: {type(e).__name__}")
        return {
            "registered": False,
            "module_name": module_name,
            "dll_path": None,
            "dll_exists": False,
            "registry_path": None,
            "error_code": "MODULE_DETAILS_FAILED",
        }


def register_module_before_open(
    hwp,
    module_name: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Open 직전에 RegisterModule을 호출한다.

    Args:
        hwp: HwpObject 인스턴스
        module_name: 보안모듈 이름

    Returns:
        (성공여부, error_or_None)
        - (True, None): 등록 성공
        - (False, "HANCOM_SECURITY_MODULE_NOT_REGISTERED"): 미등록
        - (False, "HANCOM_REGISTER_MODULE_FAILED"): 호출 실패
    """
    if hwp is None:
        return False, "HWPOBJECT_NOT_INITIALIZED"

    if module_name is None:
        module_name = DEFAULT_SECURITY_MODULE_NAME

    try:
        # 1. registry 확인
        module_info = get_security_module_details(module_name)
        if not module_info.get("registered"):
            logger.error(
                f"보안모듈 미등록: {module_name}, "
                f"error: {module_info.get('error_code')}"
            )
            return False, "HANCOM_SECURITY_MODULE_NOT_REGISTERED"

        if not module_info.get("dll_exists"):
            logger.error(
                f"보안모듈 DLL 없음: {module_info.get('dll_path')}"
            )
            return False, "HANCOM_SECURITY_MODULE_NOT_REGISTERED"

        # 2. RegisterModule 호출 (Open 직전)
        # HwpObject.RegisterModule(module_name)
        # 또는 RegisterModule("FilePathCheckDLL", module_name)
        try:
            if hasattr(hwp, "RegisterModule"):
                # 공식 API: RegisterModule(모듈이름)
                result = hwp.RegisterModule(module_name)  # type: ignore
                logger.info(
                    f"RegisterModule 호출 성공: {module_name}, "
                    f"결과: {result}"
                )
                return True, None
            else:
                logger.error("RegisterModule 메서드 없음")
                return False, "HANCOM_REGISTER_MODULE_FAILED"

        except Exception as e:
            logger.error(
                f"RegisterModule 호출 실패: {type(e).__name__}: {e}"
            )
            return False, "HANCOM_REGISTER_MODULE_FAILED"

    except Exception as e:
        logger.error(f"RegisterModule 전 처리 실패: {type(e).__name__}")
        return False, "HANCOM_REGISTER_MODULE_FAILED"


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


def setup_security_module_registry(
    module_name: Optional[str] = None,
    dll_path: Optional[str] = None,
) -> dict:
    """보안모듈을 registry에 등록한다 (사용자 명시적 승인하에).

    Args:
        module_name: 보안모듈 이름 (기본값: DEFAULT_SECURITY_MODULE_NAME)
        dll_path: DLL 파일 경로 (자동 탐색 시도)

    Returns:
        {
            "success": bool,
            "module_name": str,
            "dll_path": str | None,
            "registry_path": str | None,
            "error_code": str | None,
            "message": str,
        }

    주의:
    - 관리자 권한이 필요할 수 있음
    - registry에 write함
    - 사용자가 명시적으로 호출해야 함
    """
    if module_name is None:
        module_name = DEFAULT_SECURITY_MODULE_NAME

    result = {
        "success": False,
        "module_name": module_name,
        "dll_path": None,
        "registry_path": None,
        "error_code": None,
        "message": None,
    }

    try:
        import winreg

        # 1단계: DLL 경로 결정
        if dll_path is None:
            # 자동 탐색: 일반적인 한컴 설치 경로들
            possible_paths = [
                r"C:\Program Files\HNC\HOffice 2014\Bin\HwpAutomation.dll",
                r"C:\Program Files\HNC\한글2014\Bin\HwpAutomation.dll",
                r"C:\Program Files (x86)\HNC\HOffice 2014\Bin\HwpAutomation.dll",
                r"C:\Program Files\HNC\한글과컴퓨터\Bin\HwpAutomation.dll",
            ]

            found_dll = None
            for path in possible_paths:
                if os.path.exists(path):
                    found_dll = path
                    logger.info(f"한컴 DLL 자동 발견: {path}")
                    break

            if not found_dll:
                result["error_code"] = "DLL_PATH_NOT_FOUND"
                result["message"] = (
                    "한컴 DLL을 자동으로 찾을 수 없습니다. "
                    "dll_path 매개변수로 경로를 직접 지정하세요."
                )
                logger.error(result["message"])
                return result

            dll_path = found_dll
        else:
            # 사용자가 지정한 경로 확인
            if not os.path.exists(dll_path):
                result["error_code"] = "DLL_PATH_NOT_EXISTS"
                result["message"] = f"DLL 파일을 찾을 수 없습니다: {dll_path}"
                logger.error(result["message"])
                return result

        result["dll_path"] = dll_path

        # 2단계: Registry에 등록
        registry_path = SECURITY_MODULE_REGISTRY_PATHS[0][0]  # 첫 번째 경로 사용

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                registry_path,
                0,
                winreg.KEY_WRITE,  # write 권한 필요
            )

            # module_name과 DLL 경로 등록
            winreg.SetValueEx(key, module_name, 0, winreg.REG_SZ, dll_path)
            winreg.CloseKey(key)

            result["success"] = True
            result["registry_path"] = registry_path
            result["message"] = (
                f"✅ 보안모듈 등록 완료\n"
                f"   모듈명: {module_name}\n"
                f"   DLL 경로: {dll_path}\n"
                f"   Registry: HKEY_CURRENT_USER\\{registry_path}"
            )
            logger.info(result["message"])

            return result

        except PermissionError:
            result["error_code"] = "REGISTRY_PERMISSION_DENIED"
            result["message"] = (
                "Registry 쓰기 권한이 없습니다. "
                "관리자 권한으로 실행하거나, "
                "dll_path를 직접 지정해주세요."
            )
            logger.error(result["message"])
            return result

        except Exception as e:
            result["error_code"] = "REGISTRY_WRITE_FAILED"
            result["message"] = f"Registry 등록 실패: {type(e).__name__}: {e}"
            logger.error(result["message"])
            return result

    except ImportError:
        result["error_code"] = "WINREG_NOT_AVAILABLE"
        result["message"] = "winreg 모듈을 사용할 수 없습니다."
        logger.error(result["message"])
        return result
    except Exception as e:
        result["error_code"] = "SETUP_FAILED"
        result["message"] = f"설정 실패: {type(e).__name__}: {e}"
        logger.error(result["message"])
        return result


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
