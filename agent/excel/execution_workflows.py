"""Excel 변경 실행 워크플로우.

승인된 계획을 실행하고 복사본을 저장한다. 원본 저장은 금지된다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import batch_executor, validator

logger = logging.getLogger(__name__)


def apply_change_plan_copy(
    plan: dict,
    output_path: str,
    approval_token: str,
) -> dict:
    """승인된 계획을 복사본으로 실행한다.

    Returns:
        {
            "success": bool,
            "output_path": str | None,
            "change_log": {...},
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        # Approval 확인
        if not approval_token:
            result["error"] = "APPROVAL_REQUIRED"
            return result

        if not output_path:
            result["error"] = "OUTPUT_PATH_REQUIRED"
            return result

        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err
        from .operation_schema import ChangePlan

        # GetActiveObject로 Excel 연결
        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error"] = "NO_ACTIVE_WORKBOOK"
            return result

        try:
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # ChangePlan 복원
        try:
            # plan dict를 ChangePlan 인스턴스로 변환
            from .operation_schema import Operation
            operations = [
                Operation(
                    type=op["type"],
                    sheet=op["sheet"],
                    risk=op["risk"],
                    params=op["params"],
                )
                for op in plan.get("operations", [])
            ]

            restored_plan = ChangePlan(
                success=plan.get("success", True),
                dry_run=plan.get("dry_run", True),
                operations=operations,
                requires_approval=plan.get("requires_approval", False),
                will_modify_original=plan.get("will_modify_original", False),
                save_mode=plan.get("save_mode", "save_as"),
            )
        except Exception:  # noqa: BLE001
            result["error"] = "INVALID_PLAN"
            return result

        # 계획 실행
        success, error, exec_result = batch_executor.apply_change_plan(
            app, wb, sheet, restored_plan, output_path
        )

        if success:
            result["success"] = True
            result["output_path"] = output_path
            result["change_log"] = exec_result.get("change_log")
        else:
            result["error"] = error
            if "change_log" in exec_result:
                result["change_log"] = exec_result["change_log"]

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("apply_change_plan_copy 실패: %s", type(e).__name__)
        result["error"] = "EXECUTION_FAILED"
        return result
