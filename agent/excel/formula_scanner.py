"""수식 셀 스캔 및 분석."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def scan_formula_cells(
    sheet: Any,
    start_row: int = 1,
    end_row: int = 1000,
    start_col: int = 1,
    end_col: int = 50,
) -> tuple[Optional[list], Optional[str]]:
    """수식이 포함된 셀 목록을 스캔한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)
        start_col: 시작 열 (1-based)
        end_col: 종료 열 (1-based)

    Returns:
        ([{"row": int, "col": int, "formula": str, "value": Any}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        formula_cells = []

        for row_idx in range(start_row, end_row + 1):
            for col_idx in range(start_col, end_col + 1):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    formula = cell.Formula

                    if isinstance(formula, str) and formula.startswith("="):
                        value = cell.Value
                        formula_cells.append({
                            "row": row_idx,
                            "col": col_idx,
                            "formula": formula,
                            "value": value,
                        })
                except Exception:  # noqa: BLE001
                    pass

        return formula_cells, None

    except Exception as e:  # noqa: BLE001
        logger.error("scan_formula_cells 실패: %s", type(e).__name__)
        return None, "FORMULA_SCAN_FAILED"


def detect_numeric_as_text_candidates(
    sheet: Any,
    start_row: int = 1,
    end_row: int = 1000,
    start_col: int = 1,
    end_col: int = 50,
) -> tuple[Optional[list], Optional[str]]:
    """숫자처럼 보이는데 텍스트로 저장된 셀을 감지한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)
        start_col: 시작 열 (1-based)
        end_col: 종료 열 (1-based)

    Returns:
        ([{"row": int, "col": int, "value": str}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        candidates = []

        for row_idx in range(start_row, end_row + 1):
            for col_idx in range(start_col, end_col + 1):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    value = cell.Value

                    # 문자열 타입이면서 숫자 패턴
                    if isinstance(value, str):
                        stripped = value.strip()
                        if _looks_like_numeric(stripped):
                            candidates.append({
                                "row": row_idx,
                                "col": col_idx,
                                "value": value,
                            })
                except Exception:  # noqa: BLE001
                    pass

        return candidates, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_numeric_as_text_candidates 실패: %s", type(e).__name__)
        return None, "NUMERIC_TEXT_DETECTION_FAILED"


def _looks_like_numeric(value: str) -> bool:
    """문자열이 숫자처럼 보이는지 판정."""
    if not isinstance(value, str) or not value:
        return False

    # 숫자, 소수점, 마이너스 부호만 허용
    try:
        float(value)
        return True
    except ValueError:
        return False
