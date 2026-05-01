"""정산서 검토 워크플로우 (승인 검증 + 복사본 저장)."""
from __future__ import annotations

import logging
from typing import Optional

from . import settlement_review
from .. import validator

logger = logging.getLogger(__name__)


def review_settlement_copy(
    output_path: str,
    approval_token: str,
    header_row: Optional[int] = None,
    difference_threshold: float = 0.05,
) -> dict:
    """건설 정산서를 검토하고 복사본으로 저장한다.

    Returns:
        {
            "success": bool,
            "output_path": str | None,
            "review_summary": {...},
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

        from ..connectors.excel_com_connector import get_active_excel_app
        from .. import errors as _err

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

        # 정산서 분석
        success, error, analysis = settlement_review.analyze_settlement_sheet(sheet)
        if not success:
            result["error"] = error
            return result

        # 헤더 행 결정
        target_header_row = header_row or analysis.get("header_row")
        if not target_header_row:
            result["error"] = "HEADER_ROW_NOT_FOUND"
            return result

        # 데이터 범위
        data_start = analysis.get("data_start_row", target_header_row + 1)
        data_end = analysis.get("data_end_row", analysis.get("total_rows"))

        # 임시 구현: 청구액(col 2), 실제액(col 3) 가정
        # 실제로는 열 매핑이 필요하지만, 정산서 구조가 표준화되어있다고 가정
        settlement_issues = []
        success, _, settlement_issues = settlement_review.detect_settlement_issues(
            sheet,
            claim_col=2,  # 청구액
            actual_col=3,  # 실제액
            data_start=data_start,
            data_end=data_end,
            threshold=difference_threshold,
        )

        # 검토결과 보고서 생성
        success, error, report = settlement_review.generate_settlement_report(
            analysis, settlement_issues
        )

        if success:
            try:
                wb.SaveCopyAs(output_path)
                result["success"] = True
                result["output_path"] = output_path
                result["review_summary"] = report
            except Exception as e:  # noqa: BLE001
                logger.error("SaveCopyAs failed: %s", type(e).__name__)
                result["error"] = "SAVE_COPY_AS_FAILED"

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("review_settlement_copy 실패: %s", type(e).__name__)
        result["error"] = "REVIEW_SETTLEMENT_FAILED"
        return result
