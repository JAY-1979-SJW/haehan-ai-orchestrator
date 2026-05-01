"""Excel 보고서 워크플로우.

검토 요약 시트를 생성하고 복사본으로 저장한다. 원본 저장은 금지된다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import summary_sheet_writer, report_table_builder, validator

logger = logging.getLogger(__name__)


def create_review_summary_sheet_copy(
    output_path: str,
    approval_token: str,
    change_log: Optional[dict] = None,
    validation_report: Optional[dict] = None,
) -> dict:
    """AI 검토 요약 시트를 생성하고 복사본으로 저장한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "output_path": str | None,
            "summary": {...},
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

        # 요약 시트 생성
        sheet_name = "AI_검토결과"
        success, error, sheet_result = summary_sheet_writer.create_summary_sheet(
            wb,
            sheet_name=sheet_name,
            change_log=change_log,
            validation_report=validation_report,
        )

        if not success:
            result["error"] = error
            return result

        result["sheet_name"] = sheet_name

        # SaveCopyAs로 복사본 저장 (원본 저장 금지)
        try:
            wb.SaveCopyAs(output_path)
            result["success"] = True
            result["output_path"] = output_path
            result["summary"] = {
                "sheet_created": True,
                "copy_saved": True,
                "rows_written": sheet_result.get("row_count", 0),
            }
        except Exception as e:  # noqa: BLE001
            logger.error("SaveCopyAs failed: %s", type(e).__name__)
            result["error"] = "SAVE_COPY_AS_FAILED"

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("create_review_summary_sheet_copy 실패: %s", type(e).__name__)
        result["error"] = "REPORT_CREATION_FAILED"
        return result
