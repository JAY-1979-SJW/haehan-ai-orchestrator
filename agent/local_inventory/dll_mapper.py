"""DLL 후보 매핑.

- HwpAutomation.dll 찾기
- FilePathCheckDLL 후보
- Office COM 관련 DLL
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .filesystem_scanner import scan_file
from .policy import SCAN_PATHS

logger = logging.getLogger(__name__)


@dataclass
class DllCandidate:
    """DLL 후보."""
    path: str
    exists: bool
    size_bytes: int | None = None
    dll_type: str = "unknown"  # "hwp_automation" / "file_path_check" / "office_com"


def find_hwp_automation_dlls() -> list[DllCandidate]:
    """HwpAutomation.dll 찾기.

    Returns:
        존재하는 DLL 경로 목록
    """
    candidates = [
        r"C:\Program Files\HNC\HOffice\HwpAutomation.dll",
        r"C:\Program Files (x86)\HNC\HOffice\HwpAutomation.dll",
        r"C:\Program Files\HNC\HOffice2020\HwpAutomation.dll",
        r"C:\Program Files\HNC\HOffice2018\HwpAutomation.dll",
        r"C:\Program Files\HNC\HOffice2014\HwpAutomation.dll",
    ]

    dlls = []
    for path in candidates:
        entry = scan_file(path)
        if entry:
            dlls.append(DllCandidate(
                path=path,
                exists=True,
                size_bytes=entry.size_bytes,
                dll_type="hwp_automation",
            ))

    return dlls


def find_file_path_check_dlls() -> list[DllCandidate]:
    """FilePathCheckDLL 후보 찾기."""
    candidates = [
        r"C:\Program Files\HNC\HOffice\FilePathCheckDLL.dll",
        r"C:\Program Files (x86)\HNC\HOffice\FilePathCheckDLL.dll",
        r"C:\Program Files\HNC\HOffice2020\FilePathCheckDLL.dll",
        r"C:\Program Files\HNC\HOffice2018\FilePathCheckDLL.dll",
    ]

    dlls = []
    for path in candidates:
        entry = scan_file(path)
        if entry:
            dlls.append(DllCandidate(
                path=path,
                exists=True,
                size_bytes=entry.size_bytes,
                dll_type="file_path_check",
            ))

    return dlls


def find_office_com_dlls() -> list[DllCandidate]:
    """Office COM 관련 DLL 찾기."""
    candidates = [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE",
        r"C:\Program Files\Microsoft Office\root\Office15\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office15\EXCEL.EXE",
    ]

    dlls = []
    for path in candidates:
        entry = scan_file(path)
        if entry:
            dlls.append(DllCandidate(
                path=path,
                exists=True,
                size_bytes=entry.size_bytes,
                dll_type="office_com",
            ))

    return dlls


def map_all_dlls() -> dict[str, list[DllCandidate]]:
    """모든 DLL 후보 매핑."""
    return {
        "hwp_automation": find_hwp_automation_dlls(),
        "file_path_check": find_file_path_check_dlls(),
        "office_com": find_office_com_dlls(),
    }
