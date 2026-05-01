"""Excel 셀 수정.

대상 셀의 값을 변경하고, 변경 전/후 값을 반환한다.
저장은 호출하지 않는다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def col_letter(col_num: int) -> str:
    """열 번호를 알파벳으로 변환 (1 → A, 27 → AA)."""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + (col_num % 26)) + result
        col_num //= 26
    return result


def update_cell(
    sheet: Any,
    row: int,
    col: int,
    new_value: Any,
) -> Tuple[Optional[dict], Optional[str]]:
    """셀 값을 변경하고 old_value/new_value/cell_address를 반환.

    Args:
        sheet: Excel sheet 객체
        row: 행 번호 (1-based)
        col: 열 번호 (1-based)
        new_value: 새 값

    Returns:
        ({"old_value": ..., "new_value": ..., "cell_address": "A1"}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if row < 1 or col < 1:
        return None, "INVALID_CELL_REF"

    try:
        cell = sheet.Cells(row, col)
        old_value = cell.Value
        cell.Value = new_value

        cell_address = f"{col_letter(col)}{row}"
        return {
            "old_value": old_value,
            "new_value": new_value,
            "cell_address": cell_address,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("update_cell 실패: %s", type(e).__name__)
        return None, "CELL_WRITE_FAILED"
