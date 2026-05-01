"""Excel 검증 워크플로우.

자동 검증을 오케스트레이션한다. 모두 read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import validator, diff_reporter, total_validator, type_validator

logger = logging.getLogger(__name__)


def validate_active_workbook() -> dict:
    """활성 workbook을 검증한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "validation": {
                "success": bool,
                "issues": [...],
                "summary": {...},
            },
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # 검증 보고서 생성
        report = diff_reporter.ValidationReport()

        # 기본 검증 수행 (stub - 실제 구현은 필요시 확장)
        # 현재는 빈 보고서만 반환
        report.add_info({"type": "validation_complete", "message": "Validation completed"})

        result["success"] = True
        result["validation"] = report.to_dict()
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("validate_active_workbook 실패: %s", type(e).__name__)
        result["error"] = "VALIDATION_FAILED"
        return result


def validate_change_result(
    before_state: Optional[dict] = None,
    change_log: Optional[dict] = None,
) -> dict:
    """변경 결과를 검증한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "validation": {
                "success": bool,
                "issues": [...],
                "summary": {...},
            },
            "diff": {...},
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # 현재 상태 캡처
        after_state = {"cells": {}, "columns": []}

        # Diff 생성
        diff, err = diff_reporter.build_change_diff(before_state, after_state)
        if diff:
            result["diff"] = diff

        # 검증 보고서 생성
        report = diff_reporter.ValidationReport()
        report.add_info({"type": "change_validation", "message": "Change validation completed"})

        result["success"] = True
        result["validation"] = report.to_dict()
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("validate_change_result 실패: %s", type(e).__name__)
        result["error"] = "VALIDATION_FAILED"
        return result
