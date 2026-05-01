"""Excel to PDF 내보내기."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def export_active_sheet_to_pdf(sheet, output_path: str) -> tuple[bool, Optional[str]]:
    """현재 시트를 PDF로 내보낸다.

    Args:
        sheet: Excel sheet object
        output_path: PDF 저장 경로

    Returns:
        (성공 여부, 에러 메시지)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND"

    if not output_path:
        return False, "OUTPUT_PATH_REQUIRED"

    try:
        sheet.ExportAsFixedFormat(0, output_path)
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("ExportAsFixedFormat failed: %s", type(e).__name__)
        return False, "PDF_EXPORT_FAILED"


def export_workbook_to_pdf(wb, output_path: str) -> tuple[bool, Optional[str]]:
    """Workbook 전체를 PDF로 내보낸다.

    Args:
        wb: Excel workbook object
        output_path: PDF 저장 경로

    Returns:
        (성공 여부, 에러 메시지)
    """
    if wb is None:
        return False, "WORKBOOK_NOT_FOUND"

    if not output_path:
        return False, "OUTPUT_PATH_REQUIRED"

    try:
        wb.ExportAsFixedFormat(0, output_path)
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Workbook ExportAsFixedFormat failed: %s", type(e).__name__)
        return False, "PDF_EXPORT_FAILED"


def export_sheets_to_pdf(
    wb, sheet_names: list[str], output_path: str
) -> tuple[bool, Optional[str]]:
    """지정된 시트들을 PDF로 내보낸다.

    Args:
        wb: Excel workbook object
        sheet_names: 내보낼 시트 이름 목록
        output_path: PDF 저장 경로

    Returns:
        (성공 여부, 에러 메시지)
    """
    if wb is None:
        return False, "WORKBOOK_NOT_FOUND"

    if not output_path:
        return False, "OUTPUT_PATH_REQUIRED"

    if not sheet_names:
        return False, "SHEET_NAMES_REQUIRED"

    try:
        sheets_to_export = []
        for sheet_name in sheet_names:
            try:
                sheet = wb.Sheets(sheet_name)
                sheets_to_export.append(sheet)
            except Exception:  # noqa: BLE001
                logger.warning("Sheet not found: %s", sheet_name)

        if not sheets_to_export:
            return False, "NO_VALID_SHEETS"

        sheets_to_export[0].ExportAsFixedFormat(0, output_path)
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.error("Export sheets to PDF failed: %s", type(e).__name__)
        return False, "PDF_EXPORT_FAILED"


def validate_pdf_output_path(output_path: str) -> tuple[bool, Optional[str]]:
    """PDF 출력 경로 유효성 검증.

    Args:
        output_path: 검증할 경로

    Returns:
        (유효 여부, 에러 메시지)
    """
    if not output_path:
        return False, "OUTPUT_PATH_REQUIRED"

    if not output_path.lower().endswith(".pdf"):
        return False, "INVALID_PDF_EXTENSION"

    return True, None
