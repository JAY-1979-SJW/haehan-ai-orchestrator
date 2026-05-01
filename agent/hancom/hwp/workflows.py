"""HWP → HWPX 변환 워크플로우.

Orchestration 레이어:
1. 경로 검증 (path_policy)
2. 보안모듈 확인 (security_module)
3. 변환 실행 (converter)
4. 결과 검증 (package_validator)

거대 로직 금지: 각 모듈의 함수만 호출.
"""
from __future__ import annotations

import logging

from . import converter
from agent.hancom.hwpx import package_validator

logger = logging.getLogger(__name__)


def convert_hwp_to_hwpx_copy(params: dict) -> dict:
    """HWP 파일을 HWPX로 변환한다 (copy-based, 원본 보호).

    Args:
        params:
        {
            "input_path": str,          # 입력 HWP 파일 경로
            "output_path": str,         # 출력 HWPX 파일 경로
            "visible": bool,            # UI 표시 여부 (선택사항, 기본값: False)
            "module_name": str,         # 보안모듈 이름 (선택사항)
        }

    Returns:
        {
            "success": bool,
            "input_path": str | None,
            "output_path": str | None,
            "output_size": int | None,
            "hwpx_valid": bool,
            "hwpx_file_count": int,
            "hwpx_sections": int,
            "error": str | None,
        }
    """
    result = {
        "success": False,
        "input_path": None,
        "output_path": None,
        "output_size": None,
        "hwpx_valid": False,
        "hwpx_file_count": 0,
        "hwpx_sections": 0,
        "error": None,
    }

    try:
        # 파라미터 검증
        input_path = params.get("input_path")
        output_path = params.get("output_path")
        visible = params.get("visible", False)
        module_name = params.get("module_name")  # 보안모듈 이름 (선택사항)

        if not input_path or not output_path:
            result["error"] = "INPUT_OUTPUT_PATH_REQUIRED"
            return result

        # 1단계: HWP → HWPX 변환 (RegisterModule 자동 호출)
        logger.info(f"Starting conversion: {input_path} → {output_path}")
        conversion_result = converter.convert_hwp_to_hwpx(
            input_path=input_path,
            output_path=output_path,
            visible=visible,
            module_name=module_name,
        )

        if not conversion_result.get("success"):
            result["error"] = conversion_result.get("error", "CONVERSION_FAILED")
            return result

        result["input_path"] = conversion_result.get("input_path")
        result["output_path"] = conversion_result.get("output_path")
        result["output_size"] = conversion_result.get("output_size")

        # 2단계: 결과 HWPX 검증
        valid, val_error = package_validator.validate_hwpx_package(output_path)
        if not valid:
            result["error"] = f"HWPX_VALIDATION_FAILED:{val_error}"
            # HWPX 파일은 생성되었지만 구조가 잘못됨
            result["hwpx_valid"] = False
            return result

        result["hwpx_valid"] = True

        # 3단계: HWPX 메타데이터 추출
        structure = package_validator.get_hwpx_structure(output_path)
        result["hwpx_file_count"] = structure.get("file_count", 0)
        result["hwpx_sections"] = len(structure.get("sections", []))

        # 성공
        result["success"] = True
        logger.info(
            f"Conversion complete: {result['output_size']} bytes, "
            f"{result['hwpx_file_count']} files, {result['hwpx_sections']} sections"
        )

        return result

    except Exception as e:
        logger.error(f"Workflow failed: {type(e).__name__}: {e}")
        result["error"] = f"WORKFLOW_FAILED:{type(e).__name__}"
        return result
