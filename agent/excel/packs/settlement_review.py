"""정산서 분석 및 자동 검토 (건설/소방 업무용)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def analyze_settlement_sheet(sheet) -> tuple[bool, Optional[str], dict]:
    """정산서 시트를 분석하고 구조 파악.

    Returns:
        (성공 여부, 에러 메시지, 분석 결과 dict)
        {
            "has_header": bool,
            "header_row": int | None,
            "data_start_row": int | None,
            "data_end_row": int | None,
            "total_rows": int,
            "columns": {
                "item_name": int | None,
                "claim_amount": int | None,
                "actual_amount": int | None,
                "difference": int | None,
            }
        }
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    try:
        result = {
            "has_header": False,
            "header_row": None,
            "data_start_row": None,
            "data_end_row": None,
            "total_rows": 0,
            "columns": {
                "item_name": None,
                "claim_amount": None,
                "actual_amount": None,
                "difference": None,
            },
        }

        rows = sheet.UsedRange.Rows.Count
        result["total_rows"] = rows

        if rows < 2:
            return True, None, result

        # 1행부터 시작해서 헤더 찾기
        for r in range(1, min(rows + 1, 20)):
            cell_value = sheet.Cells(r, 1).Value
            if cell_value and ("항목" in str(cell_value) or "내용" in str(cell_value)):
                result["has_header"] = True
                result["header_row"] = r
                result["data_start_row"] = r + 1
                break

        if result["has_header"] and result["header_row"]:
            result["data_end_row"] = rows

        return True, None, result
    except Exception as e:  # noqa: BLE001
        logger.error("Settlement sheet analysis failed: %s", type(e).__name__)
        return False, "SHEET_ANALYSIS_FAILED", {}


def detect_settlement_issues(
    sheet, claim_col: int, actual_col: int, data_start: int, data_end: int, threshold: float = 0.05
) -> tuple[bool, Optional[str], list]:
    """청구액과 실제액의 차이가 threshold 이상인 행 감지 (5% 기본값).

    Returns:
        (성공 여부, 에러 메시지, 이슈 목록)
        [
            {
                "row": int,
                "claim": float | None,
                "actual": float | None,
                "difference": float,
                "percentage": float,
                "is_issue": bool,
            },
            ...
        ]
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", []

    if not (claim_col and actual_col):
        return False, "MISSING_COLUMNS", []

    try:
        results = []

        for row in range(data_start, data_end + 1):
            try:
                claim = sheet.Cells(row, claim_col).Value
                actual = sheet.Cells(row, actual_col).Value

                if claim is None or actual is None:
                    continue

                try:
                    claim_num = float(claim)
                    actual_num = float(actual)

                    difference = abs(claim_num - actual_num)
                    percentage = difference / claim_num if claim_num > 0 else 0
                    is_issue = percentage > threshold

                    results.append({
                        "row": row,
                        "claim": claim_num,
                        "actual": actual_num,
                        "difference": round(difference, 2),
                        "percentage": round(percentage * 100, 2),
                        "is_issue": is_issue,
                    })
                except (ValueError, TypeError):
                    pass
            except Exception:  # noqa: BLE001
                pass

        return True, None, results
    except Exception as e:  # noqa: BLE001
        logger.error("Settlement issue detection failed: %s", type(e).__name__)
        return False, "SETTLEMENT_ISSUE_DETECTION_FAILED", []


def generate_settlement_report(
    analysis: dict, settlement_issues: list
) -> tuple[bool, Optional[str], dict]:
    """정산서 검토결과 요약 생성.

    Returns:
        (성공 여부, 에러 메시지, 검토결과 dict)
        {
            "total_items": int,
            "discrepancy_items": int,
            "total_claim": float,
            "total_actual": float,
            "total_difference": float,
            "summary": [...]
        }
    """
    try:
        total_items = len(settlement_issues)
        discrepancy_items = len([i for i in settlement_issues if i.get("is_issue")])
        total_claim = sum([i.get("claim", 0) for i in settlement_issues])
        total_actual = sum([i.get("actual", 0) for i in settlement_issues])
        total_difference = abs(total_claim - total_actual)

        summary = []
        if total_items > 0:
            summary.append(f"총 항목: {total_items}개")
        if discrepancy_items > 0:
            summary.append(f"차이 항목: {discrepancy_items}개")
        summary.append(f"청구액 합계: {round(total_claim, 2)}")
        summary.append(f"실제액 합계: {round(total_actual, 2)}")
        summary.append(f"총 차액: {round(total_difference, 2)}")

        result = {
            "total_items": total_items,
            "discrepancy_items": discrepancy_items,
            "total_claim": round(total_claim, 2),
            "total_actual": round(total_actual, 2),
            "total_difference": round(total_difference, 2),
            "summary": summary,
        }

        return True, None, result
    except Exception as e:  # noqa: BLE001
        logger.error("Settlement report generation failed: %s", type(e).__name__)
        return False, "REPORT_GENERATION_FAILED", {}
