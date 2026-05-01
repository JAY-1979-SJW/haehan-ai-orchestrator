"""병합셀 감지."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def detect_merged_cells(sheet: Any) -> tuple[Optional[list], Optional[str]]:
    """병합셀 목록을 감지한다.

    Args:
        sheet: Excel sheet 객체

    Returns:
        ([{"first_row": int, "first_col": int, "row_count": int, "col_count": int}, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        merged_cells = []

        try:
            merged_ranges = sheet.MergedAreas
            if merged_ranges is not None:
                for merged_range in merged_ranges:
                    try:
                        first_row = merged_range.Row
                        first_col = merged_range.Column
                        row_count = merged_range.Rows.Count
                        col_count = merged_range.Columns.Count

                        merged_cells.append({
                            "first_row": first_row,
                            "first_col": first_col,
                            "row_count": row_count,
                            "col_count": col_count,
                            "last_row": first_row + row_count - 1,
                            "last_col": first_col + col_count - 1,
                        })
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass

        return merged_cells, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_merged_cells 실패: %s", type(e).__name__)
        return None, "MERGED_CELLS_DETECTION_FAILED"
