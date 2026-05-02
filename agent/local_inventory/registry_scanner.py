"""Windows Registry 스캔 (read-only).

- Uninstall registry 조회
- COM 클래스 레지스트리 조회
- HwpAutomation Modules 레지스트리 조회
"""
from __future__ import annotations

import logging
from typing import Optional

from .metadata import (
    get_registry_value,
    list_registry_subkeys,
)
from .policy import REGISTRY_PATHS

logger = logging.getLogger(__name__)


def scan_uninstall_registry() -> list[dict]:
    """HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall 조회.

    Returns:
        {name, version, install_location} dict 목록
    """
    try:
        import winreg

        programs = []
        path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ)
            try:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey_path = f"{path}\\{subkey_name}"

                        name = get_registry_value(
                            winreg.HKEY_LOCAL_MACHINE,
                            subkey_path,
                            "DisplayName",
                        )
                        if not name:
                            i += 1
                            continue

                        version = get_registry_value(
                            winreg.HKEY_LOCAL_MACHINE,
                            subkey_path,
                            "DisplayVersion",
                        )
                        install_loc = get_registry_value(
                            winreg.HKEY_LOCAL_MACHINE,
                            subkey_path,
                            "InstallLocation",
                        )

                        programs.append({
                            "name": name,
                            "version": version,
                            "install_location": install_loc,
                        })
                        i += 1

                    except OSError:
                        break

            finally:
                winreg.CloseKey(key)

        except FileNotFoundError:
            logger.warning(f"Registry path not found: {path}")

        return programs

    except ImportError:
        logger.warning("winreg not available")
        return []
    except Exception as e:
        logger.error(f"Failed to scan uninstall registry: {e}")
        return []


def scan_com_registry(class_names: list[str]) -> dict[str, bool]:
    """COM 클래스 등록 여부 조회.

    Args:
        class_names: COM ProgID 목록 (예: ["Excel.Application", "HWPFrame.HwpObject"])

    Returns:
        {class_name: registered} dict
    """
    result = {}

    for class_name in class_names:
        try:
            import winreg

            path = f"SOFTWARE\\Classes\\{class_name}\\CLSID"
            clsid = get_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                path,
                "",
            )
            result[class_name] = clsid is not None

        except Exception as e:
            logger.warning(f"Failed to check COM {class_name}: {e}")
            result[class_name] = False

    return result


def scan_hwp_modules_registry() -> dict:
    """HNC\\HOffice*\\HwpAutomation\\Modules 조회.

    Returns:
        {
            "registered": bool,
            "module_name": Optional[str],
            "dll_path": Optional[str],
        }
    """
    try:
        import winreg

        # HOffice 버전별 확인 (HOffice, HOffice2018, HOffice2014, ...)
        base_paths = [
            r"SOFTWARE\HNC\HOffice",
            r"SOFTWARE\HNC\HOffice2020",
            r"SOFTWARE\HNC\HOffice2018",
            r"SOFTWARE\HNC\HOffice2014",
        ]

        for base_path in base_paths:
            modules_path = f"{base_path}\\HwpAutomation\\Modules"

            module_name = get_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                modules_path,
                "",  # 기본값
            )

            if module_name:
                dll_path = get_registry_value(
                    winreg.HKEY_LOCAL_MACHINE,
                    modules_path,
                    "DllPath",
                )

                return {
                    "registered": True,
                    "module_name": module_name,
                    "dll_path": dll_path,
                    "registry_path": modules_path,
                }

        return {
            "registered": False,
            "module_name": None,
            "dll_path": None,
        }

    except ImportError:
        logger.warning("winreg not available")
        return {"registered": False}
    except Exception as e:
        logger.error(f"Failed to scan HWP modules registry: {e}")
        return {"registered": False}


def scan_program_registry(program: str) -> dict:
    """프로그램별 레지스트리 정보 조회.

    Args:
        program: 프로그램명 (예: "hancom", "excel", "autocad")

    Returns:
        {path, values, subkeys}
    """
    try:
        import winreg

        if program not in REGISTRY_PATHS:
            return {"path": None, "values": {}, "subkeys": []}

        registry_paths = REGISTRY_PATHS[program]

        # 리스트의 각 경로를 시도
        values = {}
        subkeys = []
        for registry_path in registry_paths:
            try:
                subkeys = list_registry_subkeys(winreg.HKEY_LOCAL_MACHINE, registry_path)
                if subkeys:
                    break
            except Exception:
                continue

        # 주요 값 조회
        for registry_path in registry_paths:
            for value_name in ["InstallPath", "Path", "DisplayVersion", "Version"]:
                try:
                    val = get_registry_value(
                        winreg.HKEY_LOCAL_MACHINE,
                        registry_path,
                        value_name,
                    )
                    if val:
                        values[value_name] = val
                        break
                except Exception:
                    continue
            if values:
                break

        return {
            "path": registry_path,
            "values": values,
            "subkeys": subkeys,
        }

    except Exception as e:
        logger.error(f"Failed to scan {program} registry: {e}")
        return {"path": None, "values": {}, "subkeys": []}
