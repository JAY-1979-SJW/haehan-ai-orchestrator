"""데이터 타입 검증."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def validate_column_types(
    sheet: Any,
    column_num: int,
    expected_type: str,  # "number", "text", "date"
    data_start_row: int,
    data_end_row: int,
) -> tuple[Optional[list], Optional[str]]:
    """특정 열의 데이터 타입이 예상과 일치하는지 검증한다.

    Args:
        sheet: Excel sheet 객체
        column_num: 열 번호 (1-based)
        expected_type: 기대 타입 ("number", "text", "date")
        data_start_row: 데이터 시작 행
        data_end_row: 데이터 종료 행

    Returns:
        ([issue_dict, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        issues = []
        numeric_as_text_cells = []
        empty_cells = []

        for row_idx in range(data_start_row, data_end_row + 1):
            try:
                cell = sheet.Cells(row_idx, column_num)
                value = cell.Value

                if value is None:
                    empty_cells.append(row_idx)
                    continue

                # 문자로 저장된 숫자 감지
                if isinstance(value, str):
                    if expected_type == "number":
                        if _looks_like_number(value):
                            numeric_as_text_cells.append((row_idx, value))
                            issues.append({
                                "severity": "warning",
                                "type": "numeric_as_text",
                                "cell": _cell_address(row_idx, column_num),
                                "message": f"숫자 값 '{value}'이(가) 텍스트로 저장되었습니다.",
                            })
            except Exception:  # noqa: BLE001
                pass

        # 빈 셀이 많으면 경고
        if len(empty_cells) > (data_end_row - data_start_row + 1) * 0.1:
            issues.append({
                "severity": "info",
                "type": "many_empty_cells",
                "column": column_num,
                "message": f"이 열에 빈 셀이 많습니다 ({len(empty_cells)}개).",
            })

        return issues, None

    except Exception as e:  # noqa: BLE001
        logger.error("validate_column_types failed: %s", type(e).__name__)
        return None, "TYPE_VALIDATION_FAILED"


def validate_required_columns(
    sheet: Any,
    headers: dict[str, int],
    required_headers: list[str],
    data_start_row: int,
    data_end_row: int,
) -> tuple[Optional[list], Optional[str]]:
    """필수 열에 값이 모두 채워져 있는지 검증한다.

    Args:
        sheet: Excel sheet 객체
        headers: {"header_name": column_num, ...}
        required_headers: ["header1", "header2", ...]
        data_start_row: 데이터 시작 행
        data_end_row: 데이터 종료 행

    Returns:
        ([issue_dict, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        issues = []

        for header_name in required_headers:
            if header_name not in headers:
                issues.append({
                    "severity": "error",
                    "type": "missing_required_column",
                    "column": header_name,
                    "message": f"필수 열 '{header_name}'이(가) 없습니다.",
                })
                continue

            col_num = headers[header_name]
            empty_cells = []

            for row_idx in range(data_start_row, data_end_row + 1):
                try:
                    cell = sheet.Cells(row_idx, col_num)
                    if cell.Value is None:
                        empty_cells.append(row_idx)
                except Exception:  # noqa: BLE001
                    pass

            if empty_cells:
                issues.append({
                    "severity": "error",
                    "type": "empty_required_cell",
                    "column": header_name,
                    "count": len(empty_cells),
                    "message": f"필수 열 '{header_name}'에 {len(empty_cells)}개의 빈 셀이 있습니다.",
                })

        return issues, None

    except Exception as e:  # noqa: BLE001
        logger.error("validate_required_columns failed: %s", type(e).__name__)
        return None, "REQUIRED_COLUMN_VALIDATION_FAILED"


def _looks_like_number(value: str) -> bool:
    """문자열이 숫자처럼 보이는지 판정."""
    if not isinstance(value, str) or not value:
        return False

    try:
        float(value)
        return True
    except ValueError:
        return False


def _cell_address(row: int, col: int) -> str:
    """행/열 번호를 셀 주소로 변환."""
    col_letter = ""
    while col > 0:
        col -= 1
        col_letter = chr(ord("A") + (col % 26)) + col_letter
        col //= 26
    return f"{col_letter}{row}"
