"""Excel 열 삽입 및 채우기.

헤더 기준으로 열을 삽입하고, 새 헤더를 입력하며, 기존 열의 서식을 복사한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def insert_column_at(
    sheet: Any,
    col_num: int,
    copy_format_from: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """특정 열 번호에 새 열을 삽입하고 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        col_num: 삽입 위치 (1-based, 이 위치에 새 열이 삽입됨)
        copy_format_from: 서식 복사 원본 열 번호 (None이면 col_num - 1)

    Returns:
        ({"inserted_col": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if col_num < 1:
        return None, "INVALID_COL_NUM"

    try:
        # 열 삽입
        sheet.Columns(col_num).Insert()

        # 서식 복사 원본 열 결정
        format_col = copy_format_from
        if format_col is None:
            format_col = col_num - 1 if col_num > 1 else col_num + 1

        if format_col > 0:
            try:
                src_range = sheet.Columns(format_col)
                dst_range = sheet.Columns(col_num)
                src_range.Copy()
                dst_range.PasteSpecial(2)  # xlFormats
            except Exception:  # noqa: BLE001
                pass

        return {"inserted_col": col_num}, None

    except Exception as e:  # noqa: BLE001
        logger.error("insert_column_at 실패: %s", type(e).__name__)
        return None, "COLUMN_INSERT_FAILED"


def insert_column_next_to_header(
    sheet: Any,
    header_row: int,
    anchor_header: str,
    anchor_col: int,
    new_header: str,
    position: str = "right",
) -> Tuple[Optional[int], Optional[str]]:
    """기준 헤더 옆에 새 열을 삽입하고 헤더명을 입력한다.

    Args:
        sheet: Excel sheet 객체
        header_row: 헤더 행 번호 (1-based)
        anchor_header: 기준 헤더명 (결과 반환용)
        anchor_col: 기준 열 번호 (1-based)
        new_header: 새 헤더명
        position: "right" | "left"

    Returns:
        (new_col_number, error_or_None)
          new_col_number는 삽입된 새 열의 번호 (1-based)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1 or anchor_col < 1:
        return None, "INVALID_PARAMS"
    if position not in ("right", "left"):
        return None, "INVALID_POSITION"
    if not isinstance(new_header, str) or not new_header.strip():
        return None, "INVALID_NEW_HEADER"

    try:
        # 삽입 위치 결정
        insert_pos = anchor_col + 1 if position == "right" else anchor_col

        # 열 삽입
        result, err = insert_column_at(sheet, insert_pos, copy_format_from=anchor_col)
        if err:
            return None, err

        # 헤더 입력
        try:
            cell = sheet.Cells(header_row, insert_pos)
            cell.Value = new_header.strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("헤더 입력 실패: %s", type(e).__name__)

        return insert_pos, None

    except Exception as e:  # noqa: BLE001
        logger.error("insert_column_next_to_header 실패: %s", type(e).__name__)
        return None, "COLUMN_INSERT_NEXT_TO_FAILED"


def fill_column_values(
    sheet: Any,
    col_num: int,
    header_row: int,
    values: list[Any],
    start_row: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 셀들을 값으로 채운다.

    Args:
        sheet: Excel sheet 객체
        col_num: 대상 열 번호 (1-based)
        header_row: 헤더 행 번호 (건너뜀)
        values: 입력할 값 리스트
        start_row: 시작 행 (None이면 header_row + 1)

    Returns:
        ({"filled_rows": int, "skipped": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if col_num < 1 or header_row < 1:
        return None, "INVALID_PARAMS"
    if not isinstance(values, list):
        return None, "INVALID_VALUES"

    try:
        start = start_row if start_row and start_row > header_row else header_row + 1
        filled = 0
        skipped = 0

        for idx, value in enumerate(values):
            try:
                cell = sheet.Cells(start + idx, col_num)
                cell.Value = value
                filled += 1
            except Exception:  # noqa: BLE001
                skipped += 1

        return {
            "filled_rows": filled,
            "skipped": skipped,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("fill_column_values 실패: %s", type(e).__name__)
        return None, "COLUMN_FILL_FAILED"
