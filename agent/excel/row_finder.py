"""Excel 행 검색.

헤더명과 셀값을 기준으로 데이터 행을 검색한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def find_row_by_header_value(
    sheet: Any,
    header_row: int,
    match_col: int,
    match_value: Any,
    max_rows: Optional[int] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """header_row 이후 행들에서 match_col 열의 값이 match_value와 같은 행을 찾는다.

    Args:
        sheet: Excel sheet 객체
        header_row: 헤더 행 번호 (1-based)
        match_col: 검색 열 번호 (1-based)
        match_value: 검색 값
        max_rows: 최대 스캔 행 수 (None이면 UsedRange 경계까지)

    Returns:
        (row_number, error_or_None)
          row_number는 1-based
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1 or match_col < 1:
        return None, "INVALID_PARAMS"

    if match_value is None:
        return None, "MATCH_VALUE_REQUIRED"

    try:
        # 최대 스캔 행 결정
        if max_rows is None:
            try:
                used_range = sheet.UsedRange
                max_row = used_range.Rows.Count + (header_row - 1)
            except Exception:  # noqa: BLE001
                max_row = header_row + 100  # fallback
        else:
            max_row = header_row + max_rows

        # 행 검색
        match_str = str(match_value).strip()

        for row_idx in range(header_row + 1, max_row + 1):
            try:
                cell = sheet.Cells(row_idx, match_col)
                value = cell.Value
                if value is not None:
                    cell_str = str(value).strip()
                    if cell_str == match_str:
                        return row_idx, None
            except Exception:  # noqa: BLE001
                pass

        return None, f"ROW_NOT_FOUND: {match_value}"

    except Exception as e:  # noqa: BLE001
        logger.debug("find_row_by_header_value 실패: %s", type(e).__name__)
        return None, "ROW_SEARCH_FAILED"
