"""개인정보 필터링.

- 경로 마스킹 (사용자명 제거)
- 민감 경로 제외
- 서버 전송 차단 표시
"""
from __future__ import annotations

import logging
import re
from copy import deepcopy

logger = logging.getLogger(__name__)

SENSITIVE_PATH_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"\.ssh", re.IGNORECASE),
    re.compile(r"\.aws", re.IGNORECASE),
    re.compile(r"\.kube", re.IGNORECASE),
]

USERNAME_PATTERN = re.compile(r"C:\\Users\\[^\\]+", re.IGNORECASE)


def mask_username(path: str) -> str:
    """사용자명을 마스킹.

    Args:
        path: 원본 경로 (예: C:\\Users\\skyjw\\...)

    Returns:
        마스킹된 경로 (예: C:\\Users\\<USER>\\...)
    """
    def replace_func(match: re.Match) -> str:
        return match.group(0).rsplit("\\", 1)[0] + "\\<USER>"

    return USERNAME_PATTERN.sub(replace_func, path)


def is_sensitive_path(path: str) -> bool:
    """경로가 민감 정보를 포함하는지 확인.

    Args:
        path: 확인할 경로

    Returns:
        민감 경로 여부
    """
    return any(pattern.search(path) for pattern in SENSITIVE_PATH_PATTERNS)


def filter_sensitive_paths(data: dict) -> dict:
    """민감 경로 제거/마스킹.

    Args:
        data: 인벤토리 데이터

    Returns:
        필터링된 데이터
    """
    filtered = deepcopy(data)

    # 프로그램 경로 마스킹
    if "programs" in filtered:
        for prog_name, prog_info in filtered["programs"].items():
            if isinstance(prog_info, dict):
                if "install_paths" in prog_info:
                    prog_info["install_paths"] = [
                        mask_username(p) for p in prog_info["install_paths"]
                    ]

                if "registry_info" in prog_info:
                    reg_info = prog_info["registry_info"]
                    if isinstance(reg_info, dict) and "values" in reg_info:
                        values = reg_info["values"]
                        for key, val in values.items():
                            if isinstance(val, str):
                                values[key] = mask_username(val)

    # DLL 경로 마스킹
    if "dlls" in filtered:
        for dll_type, dll_list in filtered["dlls"].items():
            if isinstance(dll_list, list):
                for dll in dll_list:
                    if isinstance(dll, dict) and "path" in dll:
                        dll["path"] = mask_username(dll["path"])

    # 폴더 경로 마스킹
    if "folders" in filtered:
        for folder_name, folder_info in filtered["folders"].items():
            if isinstance(folder_info, dict):
                if "path" in folder_info:
                    folder_info["path"] = mask_username(folder_info["path"])

    return filtered


def mark_no_transmit(data: dict) -> dict:
    """서버 전송 차단 표시 추가.

    Args:
        data: 인벤토리 데이터

    Returns:
        server_transmit: false 표시가 추가된 데이터
    """
    marked = deepcopy(data)

    if "metadata" not in marked:
        marked["metadata"] = {}

    marked["metadata"]["server_transmit"] = False
    marked["metadata"]["transmission_status"] = "local_only"

    return marked


def apply_privacy_filter(data: dict, mask_usernames: bool = True, mark_no_transmit_flag: bool = True) -> dict:
    """전체 개인정보 필터링 적용.

    Args:
        data: 인벤토리 데이터
        mask_usernames: 사용자명 마스킹 여부
        mark_no_transmit_flag: 서버 전송 차단 표시 여부

    Returns:
        필터링된 데이터
    """
    filtered = data

    if mask_usernames:
        filtered = filter_sensitive_paths(filtered)

    if mark_no_transmit_flag:
        filtered = mark_no_transmit(filtered)

    return filtered
