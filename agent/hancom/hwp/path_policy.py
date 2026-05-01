"""HWP/HWPX 파일 경로 검증 및 원본 보호.

정책:
- 입력 경로: HWP 파일 확장자 검증
- 출력 경로: HWPX 파일 확장자 강제
- 원본 덮어쓰기: 입력 == 출력이면 거부
- 경로 안전성: 절대 경로만 허용
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def validate_input_hwp_path(file_path: str) -> Tuple[bool, Optional[str]]:
    """입력 HWP 파일 경로 검증.

    Rules:
    - 파일 존재 확인
    - 확장자 .hwp 확인 (대소문자 무관)
    - 절대 경로 확인
    - 읽기 가능 확인

    Args:
        file_path: 검증할 파일 경로

    Returns:
        (유효성, error_or_None)
    """
    if not file_path or not isinstance(file_path, str):
        return False, "PATH_REQUIRED"

    # 절대 경로 확인
    if not os.path.isabs(file_path):
        return False, "ABSOLUTE_PATH_REQUIRED"

    # 파일 존재 확인
    if not os.path.exists(file_path):
        return False, "INPUT_FILE_NOT_FOUND"

    # 확장자 확인
    _, ext = os.path.splitext(file_path)
    if ext.lower() != ".hwp":
        return False, "INPUT_NOT_HWP_FILE"

    # 읽기 가능 확인
    if not os.access(file_path, os.R_OK):
        return False, "INPUT_NOT_READABLE"

    return True, None


def validate_output_hwpx_path(output_path: str) -> Tuple[bool, Optional[str]]:
    """출력 HWPX 파일 경로 검증.

    Rules:
    - 절대 경로 확인
    - 확장자 .hwpx 강제
    - 부모 디렉토리 존재 확인
    - 부모 디렉토리 쓰기 가능 확인

    Args:
        output_path: 검증할 출력 경로

    Returns:
        (유효성, error_or_None)
    """
    if not output_path or not isinstance(output_path, str):
        return False, "OUTPUT_PATH_REQUIRED"

    # 절대 경로 확인
    if not os.path.isabs(output_path):
        return False, "ABSOLUTE_PATH_REQUIRED"

    # 확장자 확인
    _, ext = os.path.splitext(output_path)
    if ext.lower() != ".hwpx":
        return False, "OUTPUT_MUST_BE_HWPX"

    # 부모 디렉토리 존재 및 쓰기 가능 확인
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        return False, "OUTPUT_DIR_NOT_FOUND"

    if output_dir and not os.access(output_dir, os.W_OK):
        return False, "OUTPUT_DIR_NOT_WRITABLE"

    return True, None


def check_original_overwrite(input_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
    """원본 덮어쓰기 여부 확인.

    원본과 출력이 같으면 거부.

    Args:
        input_path: 입력 파일 경로
        output_path: 출력 파일 경로

    Returns:
        (안전함, error_or_None)
    """
    try:
        # 절대 경로로 정규화
        input_abs = os.path.abspath(input_path)
        output_abs = os.path.abspath(output_path)

        # 같은 경로 확인
        if input_abs.lower() == output_abs.lower():
            return False, "OUTPUT_SAME_AS_INPUT"

        # 같은 파일 확인 (심볼릭 링크 등)
        if os.path.exists(input_abs) and os.path.exists(output_abs):
            if os.path.samefile(input_abs, output_abs):
                return False, "OUTPUT_SAME_AS_INPUT"

        return True, None

    except Exception as e:
        logger.error(f"Overwrite check failed: {type(e).__name__}")
        return False, "OVERWRITE_CHECK_FAILED"


def validate_conversion_paths(
    input_path: str,
    output_path: str,
) -> Tuple[bool, Optional[str]]:
    """입력/출력 경로를 종합 검증한다.

    Returns:
        (유효성, error_or_None)
    """
    # 입력 검증
    valid, error = validate_input_hwp_path(input_path)
    if not valid:
        return False, error

    # 출력 검증
    valid, error = validate_output_hwpx_path(output_path)
    if not valid:
        return False, error

    # 원본 덮어쓰기 확인
    safe, error = check_original_overwrite(input_path, output_path)
    if not safe:
        return False, error

    return True, None


def get_path_info(file_path: str) -> dict:
    """파일 경로 정보를 조회한다.

    Returns:
        {
            "path": str,
            "absolute_path": str,
            "directory": str,
            "filename": str,
            "extension": str,
            "exists": bool,
            "is_readable": bool,
            "is_writable": bool,
            "size": int | None,
        }
    """
    try:
        abs_path = os.path.abspath(file_path)
        dir_path = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        _, ext = os.path.splitext(filename)

        return {
            "path": file_path,
            "absolute_path": abs_path,
            "directory": dir_path,
            "filename": filename,
            "extension": ext.lower(),
            "exists": os.path.exists(abs_path),
            "is_readable": os.access(abs_path, os.R_OK) if os.path.exists(abs_path) else False,
            "is_writable": os.access(dir_path, os.W_OK) if os.path.exists(dir_path) else False,
            "size": os.path.getsize(abs_path) if os.path.exists(abs_path) else None,
        }
    except Exception as e:
        logger.error(f"Path info failed: {type(e).__name__}")
        return {
            "path": file_path,
            "error": str(type(e).__name__),
        }
