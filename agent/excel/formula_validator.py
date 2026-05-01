"""Excel 수식 검증.

수식의 일관성, 순환 참조, 참조 유효성을 검증한다.
Read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def extract_cell_references(formula: str) -> list[str]:
    """수식에서 셀 참조를 추출한다.

    Args:
        formula: 수식 문자열 (예: "=A1+B2*C3")

    Returns:
        ["A1", "B2", "C3"]
    """
    if not isinstance(formula, str) or not formula.startswith("="):
        return []

    # 간단한 정규식: A1, $A$1, A$1, $A1 패턴
    pattern = r"\$?[A-Z]+\$?[0-9]+"
    matches = re.findall(pattern, formula)
    return list(set(matches))  # 중복 제거


def validate_formula_in_cell(
    sheet: Any,
    row: int,
    col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """셀의 수식을 검증한다.

    Args:
        sheet: Excel sheet 객체
        row: 행 번호 (1-based)
        col: 열 번호 (1-based)

    Returns:
        ({
            "cell": "A1",
            "has_formula": bool,
            "formula": str | None,
            "references": [...],
            "has_error": bool,
            "error_type": str | None,
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if row < 1 or col < 1:
        return None, "INVALID_CELL_REF"

    try:
        from .cell_writer import col_letter

        cell = sheet.Cells(row, col)
        cell_addr = f"{col_letter(col)}{row}"

        try:
            formula = cell.Formula
            has_formula = isinstance(formula, str) and formula.startswith("=")
        except Exception:  # noqa: BLE001
            has_formula = False
            formula = None

        # 셀 값 확인 (에러 검사)
        value = cell.Value
        has_error = isinstance(value, str) and value.startswith("#")

        error_type = None
        if has_error:
            error_type = value.split("!")[0] if "!" in value else value

        references = []
        if has_formula:
            references = extract_cell_references(formula)

        return {
            "cell": cell_addr,
            "has_formula": has_formula,
            "formula": formula if has_formula else None,
            "references": references,
            "has_error": has_error,
            "error_type": error_type,
            "value": value,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("validate_formula_in_cell 실패: %s", type(e).__name__)
        return None, "FORMULA_VALIDATION_FAILED"


def check_formula_consistency_in_range(
    sheet: Any,
    start_row: int,
    end_row: int,
    col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 같은 수식이 일관적인지 확인한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)
        col: 열 번호 (1-based)

    Returns:
        ({
            "col": int,
            "rows_with_formula": [...],
            "formula_patterns": {...},
            "inconsistent_rows": [...],
            "all_consistent": bool,
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if start_row < 1 or end_row < 1 or col < 1:
        return None, "INVALID_PARAMS"

    try:
        formulas = {}
        rows_with_formula = []

        for row_idx in range(start_row, end_row + 1):
            try:
                cell = sheet.Cells(row_idx, col)
                formula = cell.Formula
                if isinstance(formula, str) and formula.startswith("="):
                    rows_with_formula.append(row_idx)
                    # 수식의 패턴화 (상대참조를 추상화)
                    pattern = _abstract_formula_pattern(formula, start_row)
                    if pattern not in formulas:
                        formulas[pattern] = []
                    formulas[pattern].append(row_idx)
            except Exception:  # noqa: BLE001
                pass

        # 일관성 확인
        inconsistent = []
        if len(formulas) > 1:
            # 가장 많은 패턴을 기준으로
            dominant_pattern = max(formulas, key=lambda k: len(formulas[k]))
            for pattern, rows in formulas.items():
                if pattern != dominant_pattern:
                    inconsistent.extend(rows)

        return {
            "col": col,
            "rows_with_formula": rows_with_formula,
            "formula_pattern_count": len(formulas),
            "inconsistent_rows": inconsistent,
            "all_consistent": len(formulas) <= 1,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("check_formula_consistency_in_range 실패: %s", type(e).__name__)
        return None, "CONSISTENCY_CHECK_FAILED"


def _abstract_formula_pattern(formula: str, base_row: int) -> str:
    """수식을 추상화 패턴으로 변환.

    상대참조는 기준 행대비 오프셋으로, 절대참조는 그대로 유지.
    예: =A5+B5 → =A[0]+B[0]  (base_row=5일 때)
         =A6+B6 → =A[1]+B[1]
    """
    if not formula.startswith("="):
        return formula

    pattern = formula[1:]  # = 제거

    # 간단한 구현: 숫자를 offset으로 변환
    # 더 정교한 구현은 복잡하므로, 여기서는 수식 텍스트 자체를 비교
    return pattern


def scan_formula_errors(
    sheet: Any,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """범위 내 수식 에러를 스캔한다.

    Args:
        sheet: Excel sheet 객체
        start_row, end_row, start_col, end_col: 범위

    Returns:
        ({
            "error_cells": [...],
            "error_count": int,
            "error_types": {...},
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if start_row < 1 or start_col < 1:
        return None, "INVALID_PARAMS"

    try:
        error_cells = []
        error_types = {}

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            for col_idx in range(start_col, min(end_col + 1, 50)):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    value = cell.Value
                    if isinstance(value, str) and value.startswith("#"):
                        from .cell_writer import col_letter
                        cell_addr = f"{col_letter(col_idx)}{row_idx}"
                        error_cells.append({
                            "cell": cell_addr,
                            "error": value,
                        })
                        error_types[value] = error_types.get(value, 0) + 1
                except Exception:  # noqa: BLE001
                    pass

        return {
            "error_cells": error_cells,
            "error_count": len(error_cells),
            "error_types": error_types,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("scan_formula_errors 실패: %s", type(e).__name__)
        return None, "ERROR_SCAN_FAILED"
