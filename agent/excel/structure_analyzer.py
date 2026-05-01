"""Excel 시트 구조 고도화 분석."""

from __future__ import annotations

import logging
from typing import Any, Optional

from . import (
    formula_scanner,
    hidden_filter_detector,
    merged_cell_detector,
    table_analyzer,
    table_region_detector,
)

logger = logging.getLogger(__name__)


def analyze_active_sheet_structure(sheet: Any) -> tuple[Optional[dict], Optional[str]]:
    """활성 시트의 전체 구조를 고도화해서 분석한다.

    Args:
        sheet: Excel sheet 객체

    Returns:
        ({
            "sheet_name": str,
            "used_range": {...},
            "data_range": {...},
            "merged_cells": [...],
            "hidden_rows": [...],
            "hidden_columns": [...],
            "autofilter": {...},
            "table_regions": [...],
            "header_candidates": [...],
            "total_row_candidates": [...],
            "formula_cells": [...],
            "numeric_as_text_candidates": [...],
            "analysis_summary": {...},
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        result = {
            "sheet_name": None,
            "used_range": None,
            "data_range": None,
            "merged_cells": [],
            "hidden_rows": [],
            "hidden_columns": [],
            "autofilter": None,
            "table_regions": [],
            "header_candidates": [],
            "total_row_candidates": [],
            "formula_cells": [],
            "numeric_as_text_candidates": [],
            "analysis_summary": {},
        }

        # 시트 이름
        try:
            result["sheet_name"] = sheet.Name
        except Exception:  # noqa: BLE001
            pass

        # UsedRange 분석
        used_range_info = _analyze_used_range(sheet)
        if used_range_info:
            result["used_range"] = used_range_info

        # 데이터 범위 감지 (기본 분석)
        range_result, err = table_analyzer.detect_data_range(sheet, 1)
        if range_result:
            result["data_range"] = range_result

            # 병합셀 감지
            merged, err = merged_cell_detector.detect_merged_cells(sheet)
            if isinstance(merged, list):
                result["merged_cells"] = merged

            # 숨김 행/열 감지
            scan_end_row = range_result.get("data_end_row", 1000) + 5
            hidden_rows, err = hidden_filter_detector.detect_hidden_rows(
                sheet, 1, scan_end_row
            )
            if isinstance(hidden_rows, list):
                result["hidden_rows"] = hidden_rows

            scan_end_col = range_result.get("last_col", 50) + 5
            hidden_cols, err = hidden_filter_detector.detect_hidden_columns(
                sheet, 1, scan_end_col
            )
            if isinstance(hidden_cols, list):
                result["hidden_columns"] = hidden_cols

            # AutoFilter 감지
            filter_result, err = hidden_filter_detector.detect_autofilter(sheet)
            if filter_result:
                result["autofilter"] = filter_result

            # 표 영역 감지
            table_regions, err = table_region_detector.detect_table_regions(
                sheet, 1, scan_end_row, 1, scan_end_col
            )
            if isinstance(table_regions, list):
                result["table_regions"] = table_regions

            # 헤더 행 후보 (처음 10줄)
            header_candidates, err = table_region_detector.detect_header_row_candidates(
                sheet, 1, 10
            )
            if isinstance(header_candidates, list):
                result["header_candidates"] = header_candidates

            # 합계 행 후보
            total_candidates, err = table_region_detector.detect_total_row_candidates(
                sheet, range_result.get("data_start_row", 2), scan_end_row
            )
            if isinstance(total_candidates, list):
                result["total_row_candidates"] = total_candidates

            # 수식 셀 스캔
            formula_cells, err = formula_scanner.scan_formula_cells(
                sheet, 1, scan_end_row, 1, scan_end_col
            )
            if isinstance(formula_cells, list):
                result["formula_cells"] = formula_cells

            # 숫자 텍스트 후보 스캔
            numeric_candidates, err = formula_scanner.detect_numeric_as_text_candidates(
                sheet, range_result.get("data_start_row", 2), scan_end_row, 1, scan_end_col
            )
            if isinstance(numeric_candidates, list):
                result["numeric_as_text_candidates"] = numeric_candidates

        # 분석 요약
        result["analysis_summary"] = {
            "merged_cell_count": len(result["merged_cells"]),
            "hidden_row_count": len(result["hidden_rows"]),
            "hidden_column_count": len(result["hidden_columns"]),
            "has_autofilter": result["autofilter"].get("has_filter", False) if result["autofilter"] else False,
            "table_region_count": len(result["table_regions"]),
            "header_candidate_count": len(result["header_candidates"]),
            "total_row_candidate_count": len(result["total_row_candidates"]),
            "formula_cell_count": len(result["formula_cells"]),
            "numeric_as_text_count": len(result["numeric_as_text_candidates"]),
        }

        return result, None

    except Exception as e:  # noqa: BLE001
        logger.error("analyze_active_sheet_structure 실패: %s", type(e).__name__)
        return None, "STRUCTURE_ANALYSIS_FAILED"


def _analyze_used_range(sheet: Any) -> Optional[dict]:
    """UsedRange 정보를 분석한다."""
    try:
        used_range = sheet.UsedRange
        if used_range is None:
            return None

        return {
            "first_row": used_range.Row,
            "first_col": used_range.Column,
            "row_count": used_range.Rows.Count,
            "col_count": used_range.Columns.Count,
            "last_row": used_range.Row + used_range.Rows.Count - 1,
            "last_col": used_range.Column + used_range.Columns.Count - 1,
        }
    except Exception:  # noqa: BLE001
        return None
