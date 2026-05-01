"""Operation 일괄 실행 (SaveCopyAs만, 원본 저장 금지)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from . import operation_executor
from .change_log import ChangeLogBuilder
from .operation_schema import ChangePlan

logger = logging.getLogger(__name__)


def apply_change_plan(
    app: Any,
    wb: Any,
    sheet: Any,
    plan: ChangePlan,
    output_path: str,
) -> tuple[bool, Optional[str], dict]:
    """변경 계획을 실행한다 (SaveCopyAs만, 원본 저장 금지).

    Args:
        app: Excel application 객체
        wb: Workbook 객체
        sheet: Active sheet 객체
        plan: ChangePlan 인스턴스
        output_path: 복사본 저장 경로

    Returns:
        (success: bool, error: Optional[str], result_dict)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    if not isinstance(plan, ChangePlan):
        return False, "INVALID_PLAN", {}

    if not output_path:
        return False, "OUTPUT_PATH_REQUIRED", {}

    try:
        # 변경 로그 빌더 생성
        log_builder = ChangeLogBuilder(len(plan.operations))

        # Operation 순차 실행
        for idx, operation in enumerate(plan.operations):
            success, error, details = operation_executor.execute_operation(sheet, operation)

            if success:
                log_builder.add_success(
                    operation_type=operation.type,
                    sheet=operation.sheet,
                    message=f"Operation executed successfully",
                    details=details,
                )
            else:
                # 실패 시 즉시 중단
                log_builder.add_failure(
                    operation_type=operation.type,
                    sheet=operation.sheet,
                    message=error or "Unknown error",
                    details=details,
                )
                # 실패 시 복사본 저장 생략하고 반환
                change_log = log_builder.build()
                return False, error, {"change_log": change_log.to_dict()}

        # 모든 operation 성공 - SaveCopyAs로 복사본 저장 (원본 저장 금지)
        try:
            # SaveCopyAs: 현재 workbook을 다른 이름으로 저장하되, 원본 wb는 그대로 유지
            wb.SaveCopyAs(output_path)
            log_builder.add_success(
                operation_type="save_copy_as",
                sheet=sheet.Name if hasattr(sheet, "Name") else "N/A",
                message=f"Copy saved to {output_path}",
                details={"output_path": output_path},
            )
        except Exception as e:  # noqa: BLE001
            logger.error("SaveCopyAs failed: %s", type(e).__name__)
            # SaveCopyAs 실패는 operation 실패와는 다른 문제
            log_builder.add_failure(
                operation_type="save_copy_as",
                sheet=sheet.Name if hasattr(sheet, "Name") else "N/A",
                message=f"SaveCopyAs failed: {type(e).__name__}",
                details={"error": str(e)},
            )
            change_log = log_builder.build()
            return False, "SAVE_COPY_AS_FAILED", {"change_log": change_log.to_dict()}

        # 모두 성공
        change_log = log_builder.build()
        return True, None, {
            "output_path": output_path,
            "change_log": change_log.to_dict(),
        }

    except Exception as e:  # noqa: BLE001
        logger.error("apply_change_plan failed: %s", type(e).__name__)
        return False, "EXECUTION_FAILED", {}
