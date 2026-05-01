"""Excel 행 삽입 및 채우기.

헤더 기준으로 행을 삽입하고, 값을 입력하며, 기존 행의 서식을 복사한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def insert_row_at(
    sheet: Any,
    row_num: int,
    copy_format_from: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """특정 행 번호에 새 행을 삽입하고 서식을 복사한다.

    Args:
        sheet: Excel sheet 객체
        row_num: 삽입 위치 (1-based, 이 위치에 새 행이 삽입됨)
        copy_format_from: 서식 복사 원본 행 번호 (None이면 row_num - 1)

    Returns:
        ({"inserted_row": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if row_num < 1:
        return None, "INVALID_ROW_NUM"

    try:
        # 행 삽입
        sheet.Rows(row_num).Insert()

        # 서식 복사 원본 행 결정
        format_row = copy_format_from
        if format_row is None:
            format_row = row_num - 1 if row_num > 1 else row_num + 1

        if format_row > 0:
            try:
                src_range = sheet.Rows(format_row)
                dst_range = sheet.Rows(row_num)
                src_range.Copy()
                dst_range.PasteSpecial(2)  # xlFormats
            except Exception:  # noqa: BLE001
                pass

        return {"inserted_row": row_num}, None

    except Exception as e:  # noqa: BLE001
        logger.error("insert_row_at 실패: %s", type(e).__name__)
        return None, "ROW_INSERT_FAILED"


def fill_row_by_headers(
    sheet: Any,
    row_num: int,
    values: dict,
    headers: dict,
) -> Tuple[Optional[dict], Optional[str]]:
    """헤더 매핑을 기반으로 행의 셀을 채운다.

    Args:
        sheet: Excel sheet 객체
        row_num: 대상 행 번호 (1-based)
        values: {"header_name": value, ...}
        headers: {"header_name": column_number, ...}

    Returns:
        ({"filled_cells": [...], "skipped_headers": [...]}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if row_num < 1:
        return None, "INVALID_ROW_NUM"
    if not isinstance(values, dict) or not isinstance(headers, dict):
        return None, "INVALID_VALUES_OR_HEADERS"

    try:
        filled_cells = []
        skipped = []

        for header_name, value in values.items():
            if header_name not in headers:
                skipped.append(header_name)
                continue

            col_num = headers[header_name]
            try:
                cell = sheet.Cells(row_num, col_num)
                cell.Value = value
                filled_cells.append({
                    "header": header_name,
                    "col": col_num,
                    "value": value,
                })
            except Exception:  # noqa: BLE001
                skipped.append(header_name)

        return {
            "filled_cells": filled_cells,
            "skipped_headers": skipped,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("fill_row_by_headers 실패: %s", type(e).__name__)
        return None, "ROW_FILL_FAILED"


def insert_row_by_match(
    sheet: Any,
    header_row: int,
    match_header: str,
    match_value: Any,
    match_col: int,
    position: str = "below",
) -> Tuple[Optional[int], Optional[str]]:
    """기준 값을 포함한 행을 찾은 후, 그 행 위/아래에 새 행을 삽입한다.

    Args:
        sheet: Excel sheet 객체
        header_row: 헤더 행 번호
        match_header: 검색용 헤더명 (결과 반환용)
        match_value: 검색 값
        match_col: 검색 열 번호 (1-based)
        position: "below" | "above"

    Returns:
        (new_row_number, error_or_None)
          new_row_number는 삽입된 새 행의 번호 (1-based)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1 or match_col < 1:
        return None, "INVALID_PARAMS"
    if position not in ("below", "above"):
        return None, "INVALID_POSITION"
    if match_value is None:
        return None, "MATCH_VALUE_REQUIRED"

    try:
        # 매칭 행 찾기
        match_str = str(match_value).strip()
        found_row = None

        try:
            used_range = sheet.UsedRange
            max_row = used_range.Rows.Count + (header_row - 1)
        except Exception:  # noqa: BLE001
            max_row = header_row + 100

        for row_idx in range(header_row + 1, max_row + 1):
            try:
                cell = sheet.Cells(row_idx, match_col)
                value = cell.Value
                if value is not None:
                    cell_str = str(value).strip()
                    if cell_str == match_str:
                        found_row = row_idx
                        break
            except Exception:  # noqa: BLE001
                pass

        if found_row is None:
            return None, f"ROW_NOT_FOUND: {match_value}"

        # 새 행 삽입 위치 결정
        insert_pos = found_row + 1 if position == "below" else found_row

        # 행 삽입
        result, err = insert_row_at(sheet, insert_pos, copy_format_from=found_row)
        if err:
            return None, err

        return insert_pos, None

    except Exception as e:  # noqa: BLE001
        logger.error("insert_row_by_match 실패: %s", type(e).__name__)
        return None, "ROW_INSERT_BY_MATCH_FAILED"
