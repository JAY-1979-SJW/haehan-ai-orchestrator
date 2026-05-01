"""요약 시트 작성."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def create_summary_sheet(
    wb: Any,
    sheet_name: str = "AI_검토결과",
    change_log: Optional[dict] = None,
    validation_report: Optional[dict] = None,
) -> tuple[bool, Optional[str], dict]:
    """요약 시트를 생성한다.

    Args:
        wb: Workbook 객체
        sheet_name: 생성할 시트 이름
        change_log: 변경 로그 dict
        validation_report: 검증 보고서 dict

    Returns:
        (success: bool, error: Optional[str], result_dict)
    """
    if wb is None:
        return False, "WORKBOOK_NOT_FOUND", {}

    try:
        # 기존 시트 확인
        sheets = [sheet.Name for sheet in wb.Sheets]
        if sheet_name in sheets:
            # 기존 시트 삭제 후 다시 생성
            try:
                wb.Sheets(sheet_name).Delete()
            except Exception:  # noqa: BLE001
                pass

        # 새 시트 생성
        new_sheet = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
        new_sheet.Name = sheet_name

        # 제목 행
        new_sheet.Cells(1, 1).Value = "AI 검토 결과 보고서"
        new_sheet.Cells(1, 1).Font.Bold = True
        new_sheet.Cells(1, 1).Font.Size = 14

        row = 3

        # 변경 로그 섹션
        if change_log:
            new_sheet.Cells(row, 1).Value = "변경 내역"
            new_sheet.Cells(row, 1).Font.Bold = True
            row += 1

            executed = change_log.get("executed_operations", 0)
            total = change_log.get("total_operations", 0)
            new_sheet.Cells(row, 1).Value = f"실행된 작업: {executed}/{total}"
            row += 1

            if change_log.get("success"):
                new_sheet.Cells(row, 1).Value = "상태: 완료"
            else:
                new_sheet.Cells(row, 1).Value = "상태: 실패"
                failed_at = change_log.get("failed_at_index")
                if failed_at is not None:
                    new_sheet.Cells(row + 1, 1).Value = f"실패 위치: Operation #{failed_at}"
            row += 3

        # 검증 결과 섹션
        if validation_report:
            new_sheet.Cells(row, 1).Value = "검증 결과"
            new_sheet.Cells(row, 1).Font.Bold = True
            row += 1

            summary = validation_report.get("summary", {})
            errors = summary.get("errors", 0)
            warnings = summary.get("warnings", 0)
            infos = summary.get("info", 0)

            new_sheet.Cells(row, 1).Value = f"오류: {errors}"
            new_sheet.Cells(row, 2).Value = f"경고: {warnings}"
            new_sheet.Cells(row, 3).Value = f"정보: {infos}"
            row += 2

            issues = validation_report.get("issues", [])
            if issues:
                new_sheet.Cells(row, 1).Value = "이슈 목록"
                new_sheet.Cells(row, 1).Font.Bold = True
                row += 1

                for issue in issues[:10]:  # 처음 10개만
                    severity = issue.get("severity", "unknown")
                    msg = issue.get("message", "")
                    new_sheet.Cells(row, 1).Value = severity.upper()
                    new_sheet.Cells(row, 2).Value = msg
                    row += 1

        # 시트 자동 너비 조정
        for col in range(1, 4):
            new_sheet.Columns(col).AutoFit()

        return True, None, {"sheet_name": sheet_name, "row_count": row}

    except Exception as e:  # noqa: BLE001
        logger.error("create_summary_sheet failed: %s", type(e).__name__)
        return False, "SUMMARY_SHEET_CREATION_FAILED", {}
