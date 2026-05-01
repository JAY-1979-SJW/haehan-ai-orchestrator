"""보고서 표 구성."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_change_table(
    sheet: Any,
    start_row: int,
    change_log: dict,
) -> tuple[bool, Optional[str], int]:
    """변경 내역 표를 작성한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        change_log: 변경 로그 dict

    Returns:
        (success: bool, error: Optional[str], end_row: int)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", start_row

    try:
        row = start_row

        # 헤더
        headers = ["작업", "상태", "셀/열", "메시지"]
        for col, header in enumerate(headers, 1):
            sheet.Cells(row, col).Value = header
            sheet.Cells(row, col).Font.Bold = True
        row += 1

        # 로그 항목
        logs = change_log.get("logs", [])
        for log in logs[:20]:  # 처음 20개만
            sheet.Cells(row, 1).Value = log.get("operation_type", "")
            sheet.Cells(row, 2).Value = log.get("status", "")
            sheet.Cells(row, 3).Value = log.get("sheet", "")
            sheet.Cells(row, 4).Value = log.get("message", "")
            row += 1

        return True, None, row

    except Exception as e:  # noqa: BLE001
        logger.error("build_change_table failed: %s", type(e).__name__)
        return False, "TABLE_BUILD_FAILED", start_row


def build_validation_table(
    sheet: Any,
    start_row: int,
    validation_report: dict,
) -> tuple[bool, Optional[str], int]:
    """검증 결과 표를 작성한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        validation_report: 검증 보고서 dict

    Returns:
        (success: bool, error: Optional[str], end_row: int)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", start_row

    try:
        row = start_row

        # 헤더
        headers = ["심각도", "타입", "셀", "메시지"]
        for col, header in enumerate(headers, 1):
            sheet.Cells(row, col).Value = header
            sheet.Cells(row, col).Font.Bold = True
        row += 1

        # 이슈 항목
        issues = validation_report.get("issues", [])
        for issue in issues[:20]:  # 처음 20개만
            sheet.Cells(row, 1).Value = issue.get("severity", "")
            sheet.Cells(row, 2).Value = issue.get("type", "")
            sheet.Cells(row, 3).Value = issue.get("cell", "")
            sheet.Cells(row, 4).Value = issue.get("message", "")
            row += 1

        return True, None, row

    except Exception as e:  # noqa: BLE001
        logger.error("build_validation_table failed: %s", type(e).__name__)
        return False, "TABLE_BUILD_FAILED", start_row


def build_summary_table(
    sheet: Any,
    start_row: int,
    change_log: Optional[dict] = None,
    validation_report: Optional[dict] = None,
) -> tuple[bool, Optional[str], int]:
    """요약 표를 작성한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        change_log: 변경 로그 dict
        validation_report: 검증 보고서 dict

    Returns:
        (success: bool, error: Optional[str], end_row: int)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", start_row

    try:
        row = start_row

        # 요약 제목
        sheet.Cells(row, 1).Value = "요약"
        sheet.Cells(row, 1).Font.Bold = True
        row += 1

        # 변경 요약
        if change_log:
            total = change_log.get("total_operations", 0)
            executed = change_log.get("executed_operations", 0)
            sheet.Cells(row, 1).Value = "총 작업 수"
            sheet.Cells(row, 2).Value = total
            row += 1
            sheet.Cells(row, 1).Value = "실행된 작업"
            sheet.Cells(row, 2).Value = executed
            row += 1

        # 검증 요약
        if validation_report:
            summary = validation_report.get("summary", {})
            row += 1
            sheet.Cells(row, 1).Value = "발견된 오류"
            sheet.Cells(row, 2).Value = summary.get("errors", 0)
            row += 1
            sheet.Cells(row, 1).Value = "발견된 경고"
            sheet.Cells(row, 2).Value = summary.get("warnings", 0)
            row += 1
            sheet.Cells(row, 1).Value = "정보 메시지"
            sheet.Cells(row, 2).Value = summary.get("info", 0)
            row += 1

        return True, None, row

    except Exception as e:  # noqa: BLE001
        logger.error("build_summary_table failed: %s", type(e).__name__)
        return False, "TABLE_BUILD_FAILED", start_row
