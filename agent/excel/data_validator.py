"""Excel 데이터 품질 검증.

빈 셀, 중복, 유효성, 일관성을 검사한다.
Read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def check_empty_cells_in_range(
    sheet: Any,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """범위 내 빈 셀을 검사한다.

    Args:
        sheet: Excel sheet 객체
        start_row, end_row, start_col, end_col: 범위 (1-based)

    Returns:
        ({
            "total_cells": int,
            "empty_cells": int,
            "empty_percentage": float,
            "empty_by_column": {...},
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if start_row < 1 or start_col < 1:
        return None, "INVALID_PARAMS"

    try:
        total = 0
        empty_count = 0
        empty_by_col = {}

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            for col_idx in range(start_col, min(end_col + 1, 50)):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    value = cell.Value
                    total += 1

                    if value is None or (isinstance(value, str) and not value.strip()):
                        empty_count += 1
                        if col_idx not in empty_by_col:
                            empty_by_col[col_idx] = 0
                        empty_by_col[col_idx] += 1
                except Exception:  # noqa: BLE001
                    total += 1
                    empty_count += 1

        empty_pct = (empty_count / total * 100) if total > 0 else 0

        return {
            "total_cells": total,
            "empty_cells": empty_count,
            "empty_percentage": round(empty_pct, 2),
            "empty_by_column": empty_by_col,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("check_empty_cells_in_range 실패: %s", type(e).__name__)
        return None, "EMPTY_CHECK_FAILED"


def detect_duplicates_in_column(
    sheet: Any,
    col_num: int,
    start_row: int,
    end_row: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 중복값을 감지한다.

    Args:
        sheet: Excel sheet 객체
        col_num: 열 번호 (1-based)
        start_row, end_row: 범위

    Returns:
        ({
            "col": int,
            "total_values": int,
            "unique_values": int,
            "duplicates": [{value: ..., count: ..., rows: [...]}, ...],
            "has_duplicates": bool,
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if col_num < 1 or start_row < 1:
        return None, "INVALID_PARAMS"

    try:
        values_map = {}

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            try:
                cell = sheet.Cells(row_idx, col_num)
                value = cell.Value

                if value is None or (isinstance(value, str) and not value.strip()):
                    continue

                value_str = str(value).strip()
                if value_str not in values_map:
                    values_map[value_str] = []
                values_map[value_str].append(row_idx)

            except Exception:  # noqa: BLE001
                pass

        duplicates = [
            {
                "value": v,
                "count": len(rows),
                "rows": rows,
            }
            for v, rows in sorted(values_map.items())
            if len(rows) > 1
        ]

        return {
            "col": col_num,
            "total_values": len(values_map),
            "unique_values": len([v for v, r in values_map.items() if len(r) == 1]),
            "duplicates": duplicates,
            "has_duplicates": len(duplicates) > 0,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_duplicates_in_column 실패: %s", type(e).__name__)
        return None, "DUPLICATE_DETECTION_FAILED"


def check_numeric_consistency(
    sheet: Any,
    col_num: int,
    start_row: int,
    end_row: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 숫자 일관성을 검사한다.

    Args:
        sheet: Excel sheet 객체
        col_num: 열 번호 (1-based)
        start_row, end_row: 범위

    Returns:
        ({
            "col": int,
            "numeric_count": int,
            "non_numeric_count": int,
            "min": float | None,
            "max": float | None,
            "average": float | None,
            "issues": [...],
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if col_num < 1 or start_row < 1:
        return None, "INVALID_PARAMS"

    try:
        numerics = []
        non_numerics = []
        issues = []

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            try:
                cell = sheet.Cells(row_idx, col_num)
                value = cell.Value

                if value is None:
                    continue

                if isinstance(value, (int, float)):
                    numerics.append(value)
                elif isinstance(value, str):
                    # 숫자로 파싱 가능한지 확인
                    try:
                        num_val = float(value.strip())
                        numerics.append(num_val)
                    except ValueError:
                        non_numerics.append(row_idx)
                else:
                    non_numerics.append(row_idx)

            except Exception:  # noqa: BLE001
                non_numerics.append(row_idx)

        if non_numerics and numerics:
            issues.append({
                "type": "mixed_types",
                "non_numeric_rows": non_numerics[:10],  # 최대 10개만
            })

        min_val = min(numerics) if numerics else None
        max_val = max(numerics) if numerics else None
        avg_val = (sum(numerics) / len(numerics)) if numerics else None

        return {
            "col": col_num,
            "numeric_count": len(numerics),
            "non_numeric_count": len(non_numerics),
            "min": min_val,
            "max": max_val,
            "average": round(avg_val, 2) if avg_val else None,
            "issues": issues,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("check_numeric_consistency 실패: %s", type(e).__name__)
        return None, "CONSISTENCY_CHECK_FAILED"


def validate_data_range(
    sheet: Any,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """범위 전체의 데이터 품질을 검증한다.

    Args:
        sheet: Excel sheet 객체
        start_row, end_row, start_col, end_col: 범위

    Returns:
        ({
            "total_cells": int,
            "empty_cells": int,
            "error_cells": int,
            "formula_cells": int,
            "data_cells": int,
            "quality_score": float (0-100),
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        total = 0
        empty = 0
        errors = 0
        formulas = 0
        data = 0

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            for col_idx in range(start_col, min(end_col + 1, 50)):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    value = cell.Value
                    total += 1

                    if value is None or (isinstance(value, str) and not value.strip()):
                        empty += 1
                    elif isinstance(value, str) and value.startswith("#"):
                        errors += 1
                    else:
                        # 수식 확인
                        try:
                            formula = cell.Formula
                            if isinstance(formula, str) and formula.startswith("="):
                                formulas += 1
                            else:
                                data += 1
                        except Exception:  # noqa: BLE001
                            data += 1
                except Exception:  # noqa: BLE001
                    empty += 1

        # 품질 점수 (빈 셀과 에러 셀 비율로 계산)
        bad_cells = empty + errors
        quality_score = max(0, (1 - (bad_cells / total if total > 0 else 0)) * 100)

        return {
            "total_cells": total,
            "empty_cells": empty,
            "error_cells": errors,
            "formula_cells": formulas,
            "data_cells": data,
            "quality_score": round(quality_score, 2),
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("validate_data_range 실패: %s", type(e).__name__)
        return None, "DATA_VALIDATION_FAILED"
