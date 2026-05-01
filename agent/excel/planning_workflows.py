"""Excel 변경 계획 워크플로우.

변경 계획 수립을 오케스트레이션한다. 절대 실제 수정을 하지 않는다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import change_planner, validator

logger = logging.getLogger(__name__)


def plan_changes(operations: list[dict]) -> dict:
    """변경 계획을 수립한다 (dry-run, 실제 수정 없음).

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "plan": {
                "success": bool,
                "dry_run": bool,
                "operations": [...],
                "requires_approval": bool,
                "will_modify_original": bool,
                "save_mode": str,
                "warnings": [str],
            },
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

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
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # 변경 계획 수립
        plan, err = change_planner.plan_changes(sheet, operations)
        if err or plan is None:
            result["error"] = err or "PLANNING_FAILED"
            return result

        result["success"] = True
        result["plan"] = plan.to_dict()
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("plan_changes 실패: %s", type(e).__name__)
        result["error"] = "PLANNING_FAILED"
        return result
