"""HWP → HWPX 변환 엔진.

변환 프로세스:
1. HwpObject 생성
2. 보안모듈 확인 (팝업 처리)
3. HWP 파일을 읽기 전용으로 열기
4. HWPX 형식으로 SaveAs
5. 결과 검증
6. 원본 유지

제약:
- 원본 HWP는 수정하지 않음
- read-only로만 열기
- SaveAs 사용 (FileSaveAs_S 권장)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from . import automation_connector, path_policy, security_module

logger = logging.getLogger(__name__)


def convert_hwp_to_hwpx(
    input_path: str,
    output_path: str,
    visible: bool = False,
    module_name: Optional[str] = None,
) -> dict:
    """HWP 파일을 HWPX로 변환한다 (read-only).

    Args:
        input_path: 입력 HWP 파일 경로
        output_path: 출력 HWPX 파일 경로
        visible: HwpObject UI 표시 여부 (기본값: False)
        module_name: 보안모듈 이름 (선택사항)

    Returns:
        {
            "success": bool,
            "input_path": str | None,
            "output_path": str | None,
            "output_size": int | None,
            "error": str | None,
        }
    """
    result = {
        "success": False,
        "input_path": None,
        "output_path": None,
        "output_size": None,
        "error": None,
    }

    hwp = None

    try:
        # 1. 경로 검증
        valid, error = path_policy.validate_conversion_paths(input_path, output_path)
        if not valid:
            result["error"] = error
            return result

        # 2. 보안모듈 확인
        registered, sec_error = security_module.check_security_module_registered()
        if not registered:
            logger.warning(f"Security module check: {sec_error}")
            # 보안모듈 없으면 진행하지 않음 (우회 금지)
            result["error"] = sec_error or "SECURITY_MODULE_NOT_AVAILABLE"
            return result

        # 3. HwpObject 생성
        hwp, error = automation_connector.create_hwp_object(visible=visible)
        if hwp is None:
            result["error"] = error
            return result

        # 4. HWP 파일 읽기 전용으로 열기 (RegisterModule 자동 호출)
        success, error = automation_connector.open_hwp_file(
            hwp, input_path, read_only=True, module_name=module_name
        )
        if not success:
            result["error"] = error
            return result

        # 5. HWPX로 저장
        success, error = automation_connector.save_hwp_as(
            hwp, output_path, file_format="HWPX"
        )
        if not success:
            result["error"] = error
            return result

        # 6. 출력 파일 존재 및 크기 확인
        if not os.path.exists(output_path):
            result["error"] = "OUTPUT_FILE_NOT_CREATED"
            return result

        output_size = os.path.getsize(output_path)
        if output_size == 0:
            result["error"] = "OUTPUT_FILE_EMPTY"
            return result

        # 성공
        result["success"] = True
        result["input_path"] = os.path.abspath(input_path)
        result["output_path"] = os.path.abspath(output_path)
        result["output_size"] = output_size
        logger.info(f"Conversion successful: {input_path} → {output_path} ({output_size} bytes)")

        return result

    except Exception as e:
        logger.error(f"Conversion failed: {type(e).__name__}: {e}")
        result["error"] = f"CONVERSION_FAILED:{type(e).__name__}"
        return result

    finally:
        # 정리: 파일 닫기 및 HwpObject 종료
        if hwp:
            try:
                automation_connector.close_hwp_file(hwp, save_changes=False)
            except Exception as e:
                logger.warning(f"Close failed: {type(e).__name__}")

            try:
                automation_connector.quit_hwp(hwp)
            except Exception as e:
                logger.warning(f"Quit failed: {type(e).__name__}")


def get_conversion_status(output_path: str) -> dict:
    """변환 결과 상태를 조회한다.

    Returns:
        {
            "exists": bool,
            "path": str,
            "size": int | None,
            "extension": str,
            "is_valid_hwpx": bool,  # zip 구조 확인
        }
    """
    info = path_policy.get_path_info(output_path)

    result = {
        "exists": info.get("exists", False),
        "path": output_path,
        "size": info.get("size"),
        "extension": info.get("extension", ""),
        "is_valid_hwpx": False,
    }

    # HWPX는 zip 기반이므로 magic number 확인 가능
    if result["exists"] and result["size"] and result["size"] > 100:
        try:
            with open(output_path, "rb") as f:
                magic = f.read(4)
                # ZIP magic number: 50 4B 03 04 (PK..)
                result["is_valid_hwpx"] = magic == b"PK\x03\x04"
        except Exception as e:
            logger.warning(f"Magic number check failed: {type(e).__name__}")

    return result
