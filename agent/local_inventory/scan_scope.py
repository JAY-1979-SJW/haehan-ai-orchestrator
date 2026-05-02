"""로컬 인벤토리 스캔 범위 정의.

- 스캔 scope 열거
- 제외 경로/폴더 정의
- scope별 필터링 함수
"""
from __future__ import annotations

from enum import Enum


class ScanScope(str, Enum):
    """인벤토리 스캔 범위 정의."""
    PROGRAMS = "programs"           # 설치된 프로그램 목록
    COM_REGISTRY = "com_registry"   # COM 클래스 등록 여부
    HANCOM = "hancom"               # 한컴 설치 및 버전
    OFFICE = "office"               # Office (Excel/Word) 설치 여부
    CAD = "cad"                     # AutoCAD 설치 여부
    USER_SELECTED_FOLDERS = "user_selected_folders"  # 사용자 지정 폴더


ALL_SCOPES = frozenset(ScanScope)

EXCLUDED_PATHS = {
    r"C:\Windows",
    r"C:\Windows\System32",
    r"C:\ProgramData",
    r"C:\$Recycle.Bin",
    r"C:\System Volume Information",
}

EXCLUDED_FOLDER_NAMES = {
    ".git",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
}


def is_excluded_path(path: str) -> bool:
    """절대 경로가 제외 목록에 있는지 확인."""
    path_lower = path.lower()
    return any(
        path_lower.startswith(excl.lower())
        for excl in EXCLUDED_PATHS
    )


def is_excluded_folder(folder_name: str) -> bool:
    """폴더명이 제외 목록에 있는지 확인."""
    return folder_name in EXCLUDED_FOLDER_NAMES
