"""Excel PDF 내보내기 워크플로우.

복사본 기반 PDF 내보내기. 원본 저장 금지.
"""
from __future__ import annotations

import logging
from typing import Optional

from . import pdf_exporter, validator

logger = logging.getLogger(__name__)


def export_pdf_copy(
    output_path: str,
    approval_token: str,
    export_type: str = "active_sheet",
    sheet_names: Optional[list[str]] = None,
) -> dict:
    """Workbook 또는 Sheet를 PDF로 내보낸다.

    Returns:
        {
            "success": bool,
            "output_path": str | None,
            "export_type": str,
            "error": str | None,
        }
    """
    result = validator.build_update_result()
    sheet_names = sheet_names or []

    try:
        # Approval 확인
        if not approval_token:
            result["error"] = "APPROVAL_REQUIRED"
            return result

        if not output_path:
            result["error"] = "OUTPUT_PATH_REQUIRED"
            return result

        # PDF 경로 유효성 검증
        valid, error = pdf_exporter.validate_pdf_output_path(output_path)
        if not valid:
            result["error"] = error
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

        # 내보내기 타입별 처리
        success = False
        if export_type == "active_sheet":
            try:
                sheet = wb.ActiveSheet
                if sheet is None:
                    result["error"] = _err.SHEET_NOT_FOUND
                    return result
            except Exception:  # noqa: BLE001
                result["error"] = _err.SHEET_NOT_FOUND
                return result

            success, error = pdf_exporter.export_active_sheet_to_pdf(
                sheet, output_path
            )
            if error:
                result["error"] = error
                return result

        elif export_type == "workbook":
            success, error = pdf_exporter.export_workbook_to_pdf(wb, output_path)
            if error:
                result["error"] = error
                return result

        elif export_type == "sheets":
            if not sheet_names:
                result["error"] = "SHEET_NAMES_REQUIRED"
                return result

            success, error = pdf_exporter.export_sheets_to_pdf(
                wb, sheet_names, output_path
            )
            if error:
                result["error"] = error
                return result

        else:
            result["error"] = "INVALID_EXPORT_TYPE"
            return result

        if success:
            result["success"] = True
            result["output_path"] = output_path
            result["export_type"] = export_type

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("export_pdf_copy 실패: %s", type(e).__name__)
        result["error"] = "PDF_EXPORT_FAILED"
        return result
