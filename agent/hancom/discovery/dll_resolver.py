"""한컴 HwpAutomation.dll 경로 해석.

Discovery 결과, 사용자 입력, 시스템 상태를 종합하여
최적의 DLL 경로를 결정하는 모듈.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, List, Tuple, Dict

from . import diagnostics, installation

logger = logging.getLogger(__name__)


def validate_dll_path(dll_path: str) -> Tuple[bool, Optional[str]]:
    """DLL 경로 검증.

    Args:
        dll_path: DLL 파일 경로

    Returns:
        (유효 여부, 에러 메시지)
    """
    if not dll_path:
        return False, "DLL 경로가 비어있습니다"

    if not os.path.exists(dll_path):
        return False, f"파일을 찾을 수 없습니다: {dll_path}"

    if not os.path.isfile(dll_path):
        return False, f"파일이 아닙니다: {dll_path}"

    if not os.access(dll_path, os.R_OK):
        return False, f"읽기 권한이 없습니다: {dll_path}"

    # DLL 파일명 확인
    if not dll_path.lower().endswith("hwpautomation.dll"):
        logger.warning(f"DLL 파일명이 HwpAutomation.dll과 다릅니다: {dll_path}")

    logger.info(f"DLL 경로 검증 통과: {dll_path}")
    return True, None


def resolve_dll_path_from_discovery() -> Optional[str]:
    """Discovery 결과에서 DLL 경로 추론.

    Returns:
        DLL 경로 또는 None
    """
    try:
        diag = diagnostics.diagnose_hancom_installation()

        # 1. Installation에서 찾은 DLL
        if diag["installation_status"]["primary_dll"]:
            dll_path = diag["installation_status"]["primary_dll"]
            valid, _ = validate_dll_path(dll_path)
            if valid:
                logger.info(f"Discovery에서 DLL 발견: {dll_path}")
                return dll_path

        # 2. 보안모듈에서 등록된 DLL
        if diag["security_module"]["registered"] and diag["security_module"]["details"]:
            dll_path = list(diag["security_module"]["details"].values())[0]
            valid, _ = validate_dll_path(dll_path)
            if valid:
                logger.info(f"보안모듈에서 DLL 발견: {dll_path}")
                return dll_path

        return None
    except Exception as e:
        logger.error(f"Discovery에서 DLL 경로 추론 실패: {type(e).__name__}")
        return None


def resolve_dll_path(
    user_provided_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """최적의 DLL 경로 결정.

    우선순위:
    1. 사용자가 제공한 경로
    2. Discovery 결과
    3. 표준 설치 경로들

    Args:
        user_provided_path: 사용자가 지정한 DLL 경로

    Returns:
        (DLL 경로, 상태/에러 메시지)
    """
    # 1. 사용자 경로
    if user_provided_path:
        valid, error = validate_dll_path(user_provided_path)
        if valid:
            logger.info(f"사용자 지정 DLL 경로 사용: {user_provided_path}")
            return user_provided_path, f"사용자 지정: {user_provided_path}"
        else:
            logger.error(f"사용자 경로 검증 실패: {error}")
            return None, error

    # 2. Discovery 결과
    discovery_dll = resolve_dll_path_from_discovery()
    if discovery_dll:
        logger.info(f"Discovery에서 DLL 경로 사용: {discovery_dll}")
        return discovery_dll, f"자동 탐색: {discovery_dll}"

    # 3. 표준 설치 경로들 (discovery와 동일)
    install_paths = installation.discover_installation_paths()
    for install_path in install_paths:
        dll_path = installation.find_dll_in_path(install_path)
        if dll_path:
            logger.info(f"표준 경로에서 DLL 발견: {dll_path}")
            return dll_path, f"표준 경로: {dll_path}"

    logger.error("DLL 경로를 찾을 수 없습니다")
    return None, "DLL을 찾을 수 없습니다. --dll-path로 경로를 명시 지정하세요"


def get_dll_candidates() -> Dict[str, str]:
    """사용 가능한 DLL 후보 목록 조회.

    Returns:
        {DLL 경로: 상태}
        상태: "valid", "found_but_invalid"
    """
    candidates = {}

    # Discovery 결과에서 DLL 후보 조회
    diag = diagnostics.diagnose_hancom_installation()

    # Installation에서 발견한 DLL들
    for dll_path, status in diag["installation_status"]["dll_candidates"].items():
        valid, _ = validate_dll_path(dll_path)
        candidates[dll_path] = "valid" if valid else "found_but_invalid"

    # 보안모듈에서 등록된 DLL
    for module_name, dll_path in diag["security_module"]["details"].items():
        if dll_path not in candidates:
            valid, _ = validate_dll_path(dll_path)
            candidates[dll_path] = "valid_from_security_module" if valid else "found_but_invalid"

    logger.info(f"DLL 후보: {candidates}")
    return candidates


def print_dll_resolution_info(
    resolved_path: Optional[str],
    status_message: str,
    candidates: Dict[str, str],
) -> None:
    """DLL 경로 해석 정보 출력.

    Args:
        resolved_path: 해석된 DLL 경로
        status_message: 상태 메시지
        candidates: DLL 후보 목록
    """
    print("\n[DLL 경로 해석]")
    print(f"  상태: {status_message}")

    if resolved_path:
        print(f"  ✓ 선택된 경로: {resolved_path}")
    else:
        print(f"  ✗ 유효한 경로를 찾을 수 없습니다")

    if candidates:
        print(f"\n  [후보 경로]")
        for dll_path, status in candidates.items():
            status_icon = "✓" if status.startswith("valid") else "✗"
            print(f"    {status_icon} {dll_path} ({status})")
    else:
        print(f"\n  [후보 경로]")
        print(f"    (없음)")
