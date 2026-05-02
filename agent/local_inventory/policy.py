"""로컬 인벤토리 스캔 정책.

- 허용 경로
- 제외 경로
- 파일 확장자 필터
- 스캔 깊이 제한
"""
from __future__ import annotations

from pathlib import Path
from typing import Set

# 스캔 대상 프로그램 경로 (사전정의, 무제한 아님)
SCAN_PATHS = {
    "hancom": [
        r"C:\Program Files\HNC",
        r"C:\Program Files (x86)\HNC",
    ],
    "excel": [
        r"C:\Program Files\Microsoft Office",
        r"C:\Program Files (x86)\Microsoft Office",
    ],
    "autocad": [
        r"C:\Program Files\Autodesk",
        r"C:\Program Files (x86)\Autodesk",
    ],
}

# 사용자 문서 폴더 (메타데이터만 수집)
USER_DOCUMENT_PATHS = [
    "{USERPROFILE}\\Documents",
    "{USERPROFILE}\\Downloads",
    "{USERPROFILE}\\Desktop",
    "{USERPROFILE}\\OneDrive",
]

# Registry 경로 (read-only)
REGISTRY_PATHS = {
    "hancom": [
        r"HKEY_LOCAL_MACHINE\SOFTWARE\HNC",
        r"HKEY_CURRENT_USER\Software\HNC",
    ],
    "excel": [
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Office",
    ],
    "autocad": [
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Autodesk",
    ],
    "installed_programs": [
        r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    ],
}

# 파일 확장자 필터 (수집 대상)
ALLOWED_EXTENSIONS: Set[str] = {
    # 실행파일
    ".exe", ".dll", ".ocx",
    # 문서
    ".hwp", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf",
    # 설정
    ".ini", ".config", ".xml", ".json",
}

# 제외 확장자
EXCLUDED_EXTENSIONS: Set[str] = {
    # 임시파일
    ".tmp", ".bak", ".~",
    # 시스템
    ".sys", ".drv",
    # 실행 스크립트 (보안)
    ".bat", ".cmd", ".ps1", ".vbs", ".sh",
    # 압축 (메타만)
    ".zip", ".rar", ".7z", ".tar", ".gz",
}

# 스캔 깊이 제한
MAX_DEPTH = {
    "program_files": 2,      # C:\Program Files\HNC\* (2 depth)
    "user_documents": 3,     # %USERPROFILE%\Documents\* (3 depth)
    "registry": 1,           # Registry direct keys only
}

# 제외 경로 (기본 제외, 깊은 스캔 금지)
EXCLUDED_PATHS: Set[str] = {
    r"C:\Windows",
    r"C:\System32",
    r"C:\ProgramData",
    r"C:\$Recycle.Bin",
}

# 제외 폴더명 (어디서나 제외)
EXCLUDED_FOLDER_NAMES = {
    ".git",
    ".svn",
    "__pycache__",
    "node_modules",
}


def is_allowed_extension(path: str) -> bool:
    """파일이 수집 대상 확장자인지 확인."""
    ext = Path(path).suffix.lower()

    if ext in EXCLUDED_EXTENSIONS:
        return False

    # 문서 폴더는 더 많은 확장자 허용
    if ext in ALLOWED_EXTENSIONS:
        return True

    # 기타 파일은 제외
    return False


def is_allowed_path(path: str) -> bool:
    """경로가 제외 경로에 포함되지 않는지 확인."""
    path_lower = path.lower()

    for excluded in EXCLUDED_PATHS:
        if path_lower.startswith(excluded.lower()):
            return False

    return True


def is_excluded_folder(folder_name: str) -> bool:
    """폴더명이 제외 폴더인지 확인."""
    return folder_name.lower() in EXCLUDED_FOLDER_NAMES


def get_max_depth(context: str) -> int:
    """컨텍스트에 따른 최대 스캔 깊이."""
    return MAX_DEPTH.get(context, 2)


def get_scan_paths(program: str) -> list[str]:
    """프로그램별 스캔 경로 반환."""
    return SCAN_PATHS.get(program, [])


def get_registry_paths(program: str) -> list[str]:
    """프로그램별 Registry 경로 반환."""
    return REGISTRY_PATHS.get(program, [])
