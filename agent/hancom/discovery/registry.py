"""한컴 Registry read-only 진단.

Windows Registry를 read-only로 조회하여 한컴 설치 상태, 보안모듈 등록 상태 진단.
write/modify 작업은 하지 않음.
"""
from __future__ import annotations

import logging
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


def read_registry_value(
    hkey: int,
    path: str,
    value_name: str,
) -> Optional[str]:
    """Registry 값 read-only 조회.

    Args:
        hkey: Registry hive (HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER 등)
        path: Registry path (예: r"Software\HNC\HOffice")
        value_name: 값 이름

    Returns:
        값의 데이터 또는 None
    """
    try:
        import winreg

        key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return value
    except (FileNotFoundError, OSError):
        return None
    except Exception as e:
        logger.warning(f"Registry 읽기 오류 ({path}/{value_name}): {type(e).__name__}")
        return None


def check_registry_path_exists(
    hkey: int,
    path: str,
) -> bool:
    """Registry 경로 존재 여부 확인.

    Args:
        hkey: Registry hive
        path: Registry path

    Returns:
        경로 존재 여부
    """
    try:
        import winreg

        key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
        winreg.CloseKey(key)
        return True
    except (FileNotFoundError, OSError):
        return False
    except Exception as e:
        logger.warning(f"Registry 경로 확인 오류 ({path}): {type(e).__name__}")
        return False


def list_registry_subkeys(
    hkey: int,
    path: str,
) -> List[str]:
    """Registry 하위 키 목록 조회.

    Args:
        hkey: Registry hive
        path: Registry path

    Returns:
        하위 키 이름 목록
    """
    try:
        import winreg

        key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
        subkeys = []
        idx = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, idx)
                subkeys.append(subkey_name)
                idx += 1
            except OSError:
                break
        winreg.CloseKey(key)
        return subkeys
    except (FileNotFoundError, OSError):
        return []
    except Exception as e:
        logger.warning(f"Registry 하위 키 조회 오류 ({path}): {type(e).__name__}")
        return []


def list_registry_values(
    hkey: int,
    path: str,
) -> Dict[str, str]:
    """Registry 값 목록 조회.

    Args:
        hkey: Registry hive
        path: Registry path

    Returns:
        {값_이름: 값_데이터} 딕셔너리
    """
    try:
        import winreg

        key = winreg.OpenKey(hkey, path, 0, winreg.KEY_READ)
        values = {}
        idx = 0
        while True:
            try:
                value_name, value_data, _ = winreg.EnumValue(key, idx)
                values[value_name] = value_data
                idx += 1
            except OSError:
                break
        winreg.CloseKey(key)
        return values
    except (FileNotFoundError, OSError):
        return {}
    except Exception as e:
        logger.warning(f"Registry 값 조회 오류 ({path}): {type(e).__name__}")
        return {}


def check_hancom_registry_installation() -> Dict[str, bool]:
    """한컴 Registry 설치 확인.

    Returns:
        {
            "HKEY_LOCAL_MACHINE_HOffice": bool,
            "HKEY_CURRENT_USER_HOffice": bool,
            "HKEY_LOCAL_MACHINE_Classes_HWPFrame": bool,
            "HKEY_LOCAL_MACHINE_Classes_HwpObject": bool,
        }
    """
    try:
        import winreg

        result = {
            "HKEY_LOCAL_MACHINE_HOffice": check_registry_path_exists(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\HNC\HOffice"
            ),
            "HKEY_CURRENT_USER_HOffice": check_registry_path_exists(
                winreg.HKEY_CURRENT_USER,
                r"Software\HNC\HOffice"
            ),
            "HKEY_LOCAL_MACHINE_Classes_HWPFrame": check_registry_path_exists(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Classes\HWPFrame.HwpObject"
            ),
            "HKEY_LOCAL_MACHINE_Classes_HwpObject": check_registry_path_exists(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Classes\HwpObject.HwpObject"
            ),
        }

        logger.info(f"한컴 Registry 설치 상태: {result}")
        return result
    except Exception as e:
        logger.error(f"한컴 Registry 확인 실패: {type(e).__name__}")
        return {
            "HKEY_LOCAL_MACHINE_HOffice": False,
            "HKEY_CURRENT_USER_HOffice": False,
            "HKEY_LOCAL_MACHINE_Classes_HWPFrame": False,
            "HKEY_LOCAL_MACHINE_Classes_HwpObject": False,
        }


def check_security_module_registry() -> Dict[str, any]:
    """보안모듈 Registry 상태 확인 (read-only).

    Returns:
        {
            "registered": bool,
            "module_names": [str],  # 등록된 모듈 이름들
            "registry_path_used": str | None,
            "details": {모듈명: 경로},
        }
    """
    try:
        import winreg

        result = {
            "registered": False,
            "module_names": [],
            "registry_path_used": None,
            "details": {},
        }

        # 두 가지 registry 경로 시도
        paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\HNC\HwpAutomation\Modules", "HNC 경로"),
            (winreg.HKEY_CURRENT_USER, r"Software\Hnc\HwpAutomation\Modules", "Hnc 경로"),
        ]

        for hkey, path, path_desc in paths:
            values = list_registry_values(hkey, path)
            if values:
                result["registered"] = True
                result["registry_path_used"] = path
                result["module_names"] = list(values.keys())
                result["details"] = values
                logger.info(f"보안모듈 발견 ({path_desc}): {values}")
                break

        if not result["registered"]:
            logger.info("보안모듈 미등록")

        return result
    except Exception as e:
        logger.error(f"보안모듈 Registry 확인 실패: {type(e).__name__}")
        return {
            "registered": False,
            "module_names": [],
            "registry_path_used": None,
            "details": {},
        }
