"""합계 행 검증."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def validate_total_rows(
    sheet: Any,
    data_start_row: int,
    data_end_row: int,
    total_row_indices: list[int],
) -> tuple[Optional[list], Optional[str]]:
    """합계 행이 모든 데이터 범위를 포함하는지 검증한다.

    Args:
        sheet: Excel sheet 객체
        data_start_row: 데이터 시작 행 (1-based)
        data_end_row: 데이터 종료 행 (1-based)
        total_row_indices: 합계 행 인덱스 목록

    Returns:
        ([issue_dict, ...], error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    if not isinstance(total_row_indices, list):
        return None, "INVALID_TOTAL_ROW_INDICES"

    try:
        issues = []

        for total_row in total_row_indices:
            # 합계 행의 수식들을 스캔
            for col_idx in range(1, 51):
                try:
                    cell = sheet.Cells(total_row, col_idx)
                    formula = cell.Formula

                    if isinstance(formula, str) and formula.startswith("="):
                        # SUM 함수인 경우 범위 확인
                        if "SUM" in formula.upper():
                            # 범위가 data_start_row ~ data_end_row를 포함하는지 확인
                            if _formula_includes_range(formula, data_start_row, data_end_row - 1):
                                pass  # OK
                            else:
                                issues.append({
                                    "severity": "warning",
                                    "type": "total_range_gap",
                                    "cell": _cell_address(total_row, col_idx),
                                    "message": f"합계 행의 범위가 데이터 범위({data_start_row}:{data_end_row})를 포함하지 않을 수 있습니다.",
                                })
                except Exception:  # noqa: BLE001
                    pass

        return issues, None

    except Exception as e:  # noqa: BLE001
        logger.error("validate_total_rows failed: %s", type(e).__name__)
        return None, "TOTAL_VALIDATION_FAILED"


def _formula_includes_range(formula: str, start_row: int, end_row: int) -> bool:
    """수식이 주어진 범위를 포함하는지 판정."""
    formula_upper = formula.upper()

    # 간단한 휴리스틱: SUM(A2:A100) 형태 확인
    import re
    pattern = r"SUM\s*\(\s*[A-Z]+\$?(\d+)\s*:\s*[A-Z]+\$?(\d+)\s*\)"
    matches = re.findall(pattern, formula_upper)

    if not matches:
        return True  # 수식 형태를 못 찾으면 일단 OK

    for match in matches:
        try:
            f_start = int(match[0])
            f_end = int(match[1])

            # 수식 범위가 데이터 범위를 포함하는지 확인
            if f_start <= start_row and f_end >= end_row:
                return True
        except (ValueError, TypeError):  # noqa: BLE001
            pass

    return False


def _cell_address(row: int, col: int) -> str:
    """행/열 번호를 셀 주소로 변환."""
    col_letter = ""
    while col > 0:
        col -= 1
        col_letter = chr(ord("A") + (col % 26)) + col_letter
        col //= 26
    return f"{col_letter}{row}"
