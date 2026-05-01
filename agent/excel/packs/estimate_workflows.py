"""내역서 검토 워크플로우 (승인 검증 + 복사본 저장)."""
from __future__ import annotations

import logging
from typing import Optional

from . import construction_estimate
from .. import validator

logger = logging.getLogger(__name__)


def review_estimate_copy(
    output_path: str,
    approval_token: str,
    header_row: Optional[int] = None,
) -> dict:
    """건설 내역서를 검토하고 복사본으로 저장한다.

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

        # 내역서 분석
        success, error, analysis = construction_estimate.analyze_estimate_sheet(sheet)
        if not success:
            result["error"] = error
            return result

        # 열 매핑
        target_header_row = header_row or analysis.get("header_row")
        if not target_header_row:
            result["error"] = "HEADER_ROW_NOT_FOUND"
            return result

        success, error, columns = construction_estimate.map_estimate_columns(
            sheet, target_header_row
        )
        if not success:
            result["error"] = error
            return result

        # 검증 및 이슈 감지
        data_start = analysis.get("data_start_row", target_header_row + 1)
        data_end = analysis.get("data_end_row", analysis.get("total_rows"))

        amount_validation = []
        price_anomalies = []
        missing_quantities = []
        duplicate_items = []

        if columns.get("amount") and columns.get("quantity") and columns.get("unit_price"):
            success, _, amount_validation = construction_estimate.validate_estimate_amounts(
                sheet,
                amount_col=columns["amount"],
                quantity_col=columns["quantity"],
                unit_price_col=columns["unit_price"],
                data_start=data_start,
                data_end=data_end,
            )

        if columns.get("unit_price"):
            success, _, price_anomalies = construction_estimate.detect_price_anomalies(
                sheet,
                unit_price_col=columns["unit_price"],
                data_start=data_start,
                data_end=data_end,
            )

        if columns.get("item_name") and columns.get("quantity"):
            success, _, missing_quantities = construction_estimate.detect_missing_quantities(
                sheet,
                item_col=columns["item_name"],
                quantity_col=columns["quantity"],
                data_start=data_start,
                data_end=data_end,
            )

        if columns.get("item_name"):
            success, _, duplicate_items = construction_estimate.detect_duplicate_items(
                sheet,
                item_col=columns["item_name"],
                spec_col=columns.get("spec"),
                data_start=data_start,
                data_end=data_end,
            )

        # 검토결과 요약 생성
        success, error, review = construction_estimate.generate_estimate_review(
            analysis, amount_validation, price_anomalies, missing_quantities, duplicate_items
        )

        if success:
            try:
                wb.SaveCopyAs(output_path)
                result["success"] = True
                result["output_path"] = output_path
                result["review_summary"] = review
            except Exception as e:  # noqa: BLE001
                logger.error("SaveCopyAs failed: %s", type(e).__name__)
                result["error"] = "SAVE_COPY_AS_FAILED"

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("review_estimate_copy 실패: %s", type(e).__name__)
        result["error"] = "REVIEW_ESTIMATE_FAILED"
        return result
