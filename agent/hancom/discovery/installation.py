"""한컴 설치 경로 탐색.

표준 설치 경로 및 Registry를 기반으로 한컴 설치 위치 탐색.
제한된 경로만 검색 (전체 C드라이브 무제한 검색 금지).
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# 탐색 대상 표준 설치 경로들 (제한 목록)
STANDARD_INSTALLATION_PATHS = [
    r"C:\Program Files\HNC\HOffice 2014",
    r"C:\Program Files\HNC\HOffice 2015",
    r"C:\Program Files\HNC\HOffice 2016",
    r"C:\Program Files\HNC\HOffice 2017",
    r"C:\Program Files\HNC\HOffice 2018",
    r"C:\Program Files\HNC\HOffice",
    r"C:\Program Files\HNC\한글2014",
    r"C:\Program Files\HNC\한글2015",
    r"C:\Program Files\HNC\한글",
    r"C:\Program Files (x86)\HNC\HOffice 2014",
    r"C:\Program Files (x86)\HNC\HOffice 2015",
    r"C:\Program Files (x86)\HNC\HOffice 2016",
    r"C:\Program Files (x86)\HNC\HOffice 2017",
    r"C:\Program Files (x86)\HNC\HOffice 2018",
    r"C:\Program Files (x86)\HNC\HOffice",
    r"C:\Program Files (x86)\HNC\한글2014",
    r"C:\Program Files (x86)\HNC\한글2015",
    r"C:\Program Files (x86)\HNC\한글",
]

# DLL 후보 파일명들
DLL_CANDIDATES = [
    "HwpAutomation.dll",
]

# DLL 탐색 대상 하위 디렉토리
SEARCH_SUBDIRS = [
    "Bin",
    "bin",
    "",  # 설치 경로 직접
]


def check_path_exists(path: str) -> bool:
    """경로 존재 여부 확인.

    Args:
        path: 파일 또는 디렉토리 경로

    Returns:
        존재 여부
    """
    try:
        return os.path.exists(path)
    except Exception as e:
        logger.warning(f"경로 확인 오류 ({path}): {type(e).__name__}")
        return False


def check_file_readable(path: str) -> bool:
    """파일 읽기 가능 여부 확인.

    Args:
        path: 파일 경로

    Returns:
        읽기 가능 여부
    """
    try:
        return os.path.isfile(path) and os.access(path, os.R_OK)
    except Exception as e:
        logger.warning(f"파일 읽기 가능성 확인 오류 ({path}): {type(e).__name__}")
        return False


def find_dll_in_path(install_path: str) -> Optional[str]:
    """설치 경로에서 HwpAutomation.dll 찾기.

    Args:
        install_path: 한컴 설치 경로 후보

    Returns:
        DLL 경로 또는 None
    """
    if not check_path_exists(install_path):
        return None

    for subdir in SEARCH_SUBDIRS:
        for dll_name in DLL_CANDIDATES:
            if subdir:
                dll_path = os.path.join(install_path, subdir, dll_name)
            else:
                dll_path = os.path.join(install_path, dll_name)

            if check_file_readable(dll_path):
                logger.info(f"DLL 발견: {dll_path}")
                return dll_path

    return None


def find_dll_from_registry() -> Optional[str]:
    """Registry의 보안모듈 정보에서 DLL 경로 추출.

    Returns:
        DLL 경로 또는 None
    """
    try:
        from . import registry

        sec_module_info = registry.check_security_module_registry()
        if sec_module_info["registered"] and sec_module_info["details"]:
            # 첫 번째 등록된 DLL 경로 반환
            dll_path = list(sec_module_info["details"].values())[0]
            if check_file_readable(dll_path):
                logger.info(f"Registry에서 DLL 발견: {dll_path}")
                return dll_path

        return None
    except Exception as e:
        logger.warning(f"Registry에서 DLL 조회 실패: {type(e).__name__}")
        return None


def discover_installation_paths() -> List[str]:
    """존재하는 한컴 설치 경로 목록 조회.

    Returns:
        [설치 경로, ...]
    """
    found_paths = []
    for path in STANDARD_INSTALLATION_PATHS:
        if check_path_exists(path):
            found_paths.append(path)
            logger.info(f"설치 경로 발견: {path}")

    if not found_paths:
        logger.warning("한컴 설치 경로를 찾을 수 없음")

    return found_paths


def discover_dll_candidates() -> Dict[str, str]:
    """DLL 후보 경로 발견.

    Returns:
        {경로: 상태}
        상태: "found_readable", "found_readable_from_registry", "not_found"
    """
    candidates = {}

    # 1. 표준 경로에서 DLL 검색
    install_paths = discover_installation_paths()
    for install_path in install_paths:
        dll_path = find_dll_in_path(install_path)
        if dll_path:
            candidates[dll_path] = "found_readable"

    # 2. Registry의 보안모듈 정보에서 DLL 경로 추출
    if not candidates:
        dll_path = find_dll_from_registry()
        if dll_path:
            candidates[dll_path] = "found_readable_from_registry"

    if candidates:
        logger.info(f"DLL 후보: {candidates}")
    else:
        logger.warning("DLL을 찾을 수 없음")

    return candidates


def diagnose_installation_status() -> Dict[str, any]:
    """한컴 설치 상태 종합 진단.

    Returns:
        {
            "installation_paths": [...],
            "dll_candidates": {...},
            "primary_dll": str | None,
        }
    """
    result = {
        "installation_paths": [],
        "dll_candidates": {},
        "primary_dll": None,
    }

    result["installation_paths"] = discover_installation_paths()
    result["dll_candidates"] = discover_dll_candidates()

    # 첫 번째 찾은 DLL을 primary로 설정
    if result["dll_candidates"]:
        result["primary_dll"] = list(result["dll_candidates"].keys())[0]

    logger.info(f"설치 상태 진단: {result['primary_dll']}")
    return result
