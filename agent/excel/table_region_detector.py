"""표 영역 감지."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def detect_table_regions(
    sheet: Any,
    start_row: int = 1,
    end_row: int = 1000,
    start_col: int = 1,
    end_col: int = 50,
) -> tuple[Optional[list], Optional[str]]:
    """표 영역 후보들을 감지한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)
        start_col: 시작 열 (1-based)
        end_col: 종료 열 (1-based)

    Returns:
        ([{"first_row": int, "first_col": int, "last_row": int, "last_col": int, "type": str}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        regions = []

        # 표 객체 감지
        try:
            list_objects = sheet.ListObjects
            if list_objects is not None:
                for tbl in list_objects:
                    try:
                        range_obj = tbl.Range
                        if range_obj is not None:
                            regions.append({
                                "first_row": range_obj.Row,
                                "first_col": range_obj.Column,
                                "last_row": range_obj.Row + range_obj.Rows.Count - 1,
                                "last_col": range_obj.Column + range_obj.Columns.Count - 1,
                                "type": "table_object",
                                "name": tbl.Name if hasattr(tbl, "Name") else None,
                            })
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

        return regions, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_table_regions 실패: %s", type(e).__name__)
        return None, "TABLE_REGIONS_DETECTION_FAILED"


def detect_header_row_candidates(
    sheet: Any,
    start_row: int = 1,
    end_row: int = 10,
) -> tuple[Optional[list], Optional[str]]:
    """헤더가 여러 줄인 경우 후보를 감지한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)

    Returns:
        ([{"row": int, "is_merged": bool, "has_content": bool}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        candidates = []

        for row_idx in range(start_row, end_row + 1):
            try:
                # 행에 내용이 있는지 확인
                has_content = False
                for col_idx in range(1, 51):
                    try:
                        cell = sheet.Cells(row_idx, col_idx)
                        if cell.Value is not None:
                            has_content = True
                            break
                    except Exception:  # noqa: BLE001
                        pass

                if has_content:
                    # 병합셀 확인
                    try:
                        is_merged = False
                        merged_ranges = sheet.MergedAreas
                        if merged_ranges is not None:
                            for merged_range in merged_ranges:
                                try:
                                    if merged_range.Row <= row_idx <= merged_range.Row + merged_range.Rows.Count - 1:
                                        is_merged = True
                                        break
                                except Exception:  # noqa: BLE001
                                    pass

                        candidates.append({
                            "row": row_idx,
                            "is_merged": is_merged,
                            "has_content": True,
                        })
                    except Exception:  # noqa: BLE001
                        candidates.append({
                            "row": row_idx,
                            "is_merged": False,
                            "has_content": True,
                        })
            except Exception:  # noqa: BLE001
                pass

        return candidates, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_header_row_candidates 실패: %s", type(e).__name__)
        return None, "HEADER_ROW_CANDIDATES_DETECTION_FAILED"


def detect_total_row_candidates(
    sheet: Any,
    data_start_row: int,
    data_end_row: int,
) -> tuple[Optional[list], Optional[str]]:
    """합계 행 후보를 감지한다.

    Args:
        sheet: Excel sheet 객체
        data_start_row: 데이터 시작 행 (1-based)
        data_end_row: 데이터 종료 행 (1-based)

    Returns:
        ([{"row": int, "indicators": [str, ...]}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        candidates = []

        # 마지막 행 주변만 확인
        check_start = max(data_start_row, data_end_row - 5)
        check_end = data_end_row + 2

        for row_idx in range(check_start, min(check_end, 1001)):
            try:
                indicators = []
                formula_count = 0
                content_count = 0

                for col_idx in range(1, 51):
                    try:
                        cell = sheet.Cells(row_idx, col_idx)
                        value = cell.Value
                        formula = cell.Formula

                        if value is not None:
                            content_count += 1

                        if isinstance(formula, str) and formula.startswith("="):
                            formula_count += 1

                            # 합계 함수 확인
                            if any(fn in formula.upper() for fn in ["SUM", "SUBTOTAL", "TOTAL"]):
                                indicators.append("has_sum_function")
                    except Exception:  # noqa: BLE001
                        pass

                # 합계 행 가능성이 있으면 추가
                if formula_count > 0 or any("total" in str(cell.Value or "").lower() for col_idx in range(1, 6)):
                    indicators.append(f"formula_count_{formula_count}")
                    candidates.append({
                        "row": row_idx,
                        "indicators": indicators,
                        "formula_count": formula_count,
                        "content_count": content_count,
                    })
            except Exception:  # noqa: BLE001
                pass

        return candidates, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_total_row_candidates 실패: %s", type(e).__name__)
        return None, "TOTAL_ROW_DETECTION_FAILED"
