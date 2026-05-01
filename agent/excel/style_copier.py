"""Excel 서식 복사.

행, 열, 셀의 서식을 복사한다 (border, font, fill, number format 등).
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def copy_row_format(
    sheet: Any,
    src_row: int,
    dst_row: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """행의 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        src_row: 원본 행 번호 (1-based)
        dst_row: 대상 행 번호 (1-based)

    Returns:
        ({"src_row": int, "dst_row": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if src_row < 1 or dst_row < 1:
        return None, "INVALID_ROW_NUM"

    try:
        src_range = sheet.Rows(src_row)
        dst_range = sheet.Rows(dst_row)
        src_range.Copy()
        # xlFormats = 2: 서식만 복사 (값 제외)
        dst_range.PasteSpecial(2)
        return {"src_row": src_row, "dst_row": dst_row}, None
    except Exception as e:  # noqa: BLE001
        logger.error("copy_row_format 실패: %s", type(e).__name__)
        return None, "ROW_FORMAT_COPY_FAILED"


def copy_column_format(
    sheet: Any,
    src_col: int,
    dst_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        src_col: 원본 열 번호 (1-based)
        dst_col: 대상 열 번호 (1-based)

    Returns:
        ({"src_col": int, "dst_col": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if src_col < 1 or dst_col < 1:
        return None, "INVALID_COL_NUM"

    try:
        src_range = sheet.Columns(src_col)
        dst_range = sheet.Columns(dst_col)
        src_range.Copy()
        # xlFormats = 2: 서식만 복사
        dst_range.PasteSpecial(2)
        return {"src_col": src_col, "dst_col": dst_col}, None
    except Exception as e:  # noqa: BLE001
        logger.error("copy_column_format 실패: %s", type(e).__name__)
        return None, "COLUMN_FORMAT_COPY_FAILED"


def copy_cell_format(
    sheet: Any,
    src_row: int,
    src_col: int,
    dst_row: int,
    dst_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """셀의 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        src_row: 원본 행 (1-based)
        src_col: 원본 열 (1-based)
        dst_row: 대상 행 (1-based)
        dst_col: 대상 열 (1-based)

    Returns:
        ({"src": "A1", "dst": "B1"}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if src_row < 1 or src_col < 1 or dst_row < 1 or dst_col < 1:
        return None, "INVALID_CELL_REF"

    try:
        from .cell_writer import col_letter

        src_cell = sheet.Cells(src_row, src_col)
        dst_cell = sheet.Cells(dst_row, dst_col)
        src_cell.Copy()
        # xlFormats = 2: 서식만 복사
        dst_cell.PasteSpecial(2)

        src_addr = f"{col_letter(src_col)}{src_row}"
        dst_addr = f"{col_letter(dst_col)}{dst_row}"
        return {"src": src_addr, "dst": dst_addr}, None

    except Exception as e:  # noqa: BLE001
        logger.error("copy_cell_format 실패: %s", type(e).__name__)
        return None, "CELL_FORMAT_COPY_FAILED"


def copy_range_format(
    sheet: Any,
    src_range_addr: str,
    dst_range_addr: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """범위의 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        src_range_addr: 원본 범위 (예: "A1:D10")
        dst_range_addr: 대상 범위 시작 주소 (예: "F1")

    Returns:
        ({"src": "A1:D10", "dst": "F1"}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if not src_range_addr or not dst_range_addr:
        return None, "INVALID_RANGE_ADDR"

    try:
        src_range = sheet.Range(src_range_addr)
        dst_range = sheet.Range(dst_range_addr)
        src_range.Copy()
        # xlFormats = 2: 서식만 복사
        dst_range.PasteSpecial(2)
        return {"src": src_range_addr, "dst": dst_range_addr}, None

    except Exception as e:  # noqa: BLE001
        logger.error("copy_range_format 실패: %s", type(e).__name__)
        return None, "RANGE_FORMAT_COPY_FAILED"
