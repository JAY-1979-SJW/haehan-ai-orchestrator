"""자재 단가 검증 워크플로우 (승인 검증 + 복사본 저장)."""
from __future__ import annotations

import logging
from typing import Optional

from . import material_price_check
from .. import validator

logger = logging.getLogger(__name__)


def check_material_prices_copy(
    output_path: str,
    approval_token: str,
    material_col: Optional[int] = None,
    unit_price_col: Optional[int] = None,
    outlier_threshold: float = 2.0,
) -> dict:
    """자재 단가를 검증하고 복사본으로 저장한다.

    Returns:
        {
            "success": bool,
            "output_path": str | None,
            "analysis_summary": {...},
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

        # 기본값 설정 (자재명: 1열, 단가: 2열 가정)
        target_material_col = material_col or 1
        target_price_col = unit_price_col or 2

        # 데이터 범위 (2행부터 끝까지 가정)
        try:
            data_end = sheet.UsedRange.Rows.Count
        except Exception:  # noqa: BLE001
            data_end = 1000

        data_start = 2

        # 자재 단가 분석
        success, error, price_analysis = material_price_check.analyze_material_prices(
            sheet,
            material_col=target_material_col,
            unit_price_col=target_price_col,
            data_start=data_start,
            data_end=data_end,
        )

        if not success:
            result["error"] = error
            return result

        # 단가 일관성 검사
        success, error, consistency_results = material_price_check.check_price_consistency(
            sheet,
            material_col=target_material_col,
            unit_price_col=target_price_col,
            data_start=data_start,
            data_end=data_end,
        )

        # 이상치 감지
        success, error, outliers = material_price_check.detect_price_outliers(
            sheet,
            unit_price_col=target_price_col,
            data_start=data_start,
            data_end=data_end,
            std_dev_threshold=outlier_threshold,
        )

        # 분석 요약
        inconsistency_count = len([c for c in consistency_results if c.get("is_inconsistent")])
        outlier_count = len([o for o in outliers if o.get("is_outlier")])

        analysis_summary = {
            "unique_materials": price_analysis.get("unique_materials", 0),
            "inconsistency_items": inconsistency_count,
            "outlier_items": outlier_count,
            "price_variations": len(price_analysis.get("price_variations", {})),
        }

        try:
            wb.SaveCopyAs(output_path)
            result["success"] = True
            result["output_path"] = output_path
            result["analysis_summary"] = analysis_summary
        except Exception as e:  # noqa: BLE001
            logger.error("SaveCopyAs failed: %s", type(e).__name__)
            result["error"] = "SAVE_COPY_AS_FAILED"

        return result

    except Exception as e:  # noqa: BLE001
        logger.error("check_material_prices_copy 실패: %s", type(e).__name__)
        result["error"] = "PRICE_CHECK_FAILED"
        return result
