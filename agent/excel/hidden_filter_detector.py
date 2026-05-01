"""숨김 행/열 및 필터 감지."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def detect_hidden_rows(sheet: Any, start_row: int = 1, end_row: int = 1000) -> tuple[Optional[list], Optional[str]]:
    """숨김 행 목록을 감지한다.

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based)

    Returns:
        ([row_num, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        hidden_rows = []

        for row_idx in range(start_row, end_row + 1):
            try:
                row = sheet.Rows(row_idx)
                if row.Hidden:
                    hidden_rows.append(row_idx)
            except Exception:  # noqa: BLE001
                pass

        return hidden_rows, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_hidden_rows 실패: %s", type(e).__name__)
        return None, "HIDDEN_ROWS_DETECTION_FAILED"


def detect_hidden_columns(sheet: Any, start_col: int = 1, end_col: int = 50) -> tuple[Optional[list], Optional[str]]:
    """숨김 열 목록을 감지한다.

    Args:
        sheet: Excel sheet 객체
        start_col: 시작 열 (1-based)
        end_col: 종료 열 (1-based)

    Returns:
        ([col_num, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        hidden_columns = []

        for col_idx in range(start_col, end_col + 1):
            try:
                col = sheet.Columns(col_idx)
                if col.Hidden:
                    hidden_columns.append(col_idx)
            except Exception:  # noqa: BLE001
                pass

        return hidden_columns, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_hidden_columns 실패: %s", type(e).__name__)
        return None, "HIDDEN_COLUMNS_DETECTION_FAILED"


def detect_autofilter(sheet: Any) -> tuple[Optional[dict], Optional[str]]:
    """AutoFilter 적용 여부를 감지한다.

    Args:
        sheet: Excel sheet 객체

    Returns:
        ({
            "has_filter": bool,
            "filter_range": {"first_row": int, "first_col": int, "last_row": int, "last_col": int} | None,
            "filtered_columns": [col_num, ...],
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        result = {
            "has_filter": False,
            "filter_range": None,
            "filtered_columns": [],
        }

        try:
            auto_filter = sheet.AutoFilter
            if auto_filter is not None:
                result["has_filter"] = True

                # 필터 범위 감지
                try:
                    filter_range = auto_filter.Range
                    if filter_range is not None:
                        result["filter_range"] = {
                            "first_row": filter_range.Row,
                            "first_col": filter_range.Column,
                            "last_row": filter_range.Row + filter_range.Rows.Count - 1,
                            "last_col": filter_range.Column + filter_range.Columns.Count - 1,
                        }

                        # 필터가 적용된 열 감지
                        try:
                            for col_idx in range(
                                result["filter_range"]["first_col"],
                                result["filter_range"]["last_col"] + 1
                            ):
                                try:
                                    col_field = auto_filter.Filters(col_idx - result["filter_range"]["first_col"] + 1)
                                    if col_field is not None and not col_field.On:
                                        result["filtered_columns"].append(col_idx)
                                except Exception:  # noqa: BLE001
                                    pass
                        except Exception:  # noqa: BLE001
                            pass
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

        return result, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_autofilter 실패: %s", type(e).__name__)
        return None, "AUTOFILTER_DETECTION_FAILED"
