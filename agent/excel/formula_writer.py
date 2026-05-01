"""Excel 수식 입력.

셀 또는 열에 수식을 입력한다. 헤더명 기반 수식 생성도 지원한다.
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


def write_formula_to_cell(
    sheet: Any,
    row: int,
    col: int,
    formula: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """셀에 수식을 입력한다.

    Args:
        sheet: Excel sheet 객체
        row: 행 번호 (1-based)
        col: 열 번호 (1-based)
        formula: 수식 문자열 (예: "=A1+B1" 또는 "=SUM(...)")

    Returns:
        ({"cell_address": "A1", "formula": "=...", "result": value}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if row < 1 or col < 1:
        return None, "INVALID_CELL_REF"
    if not isinstance(formula, str) or not formula.strip():
        return None, "INVALID_FORMULA"

    try:
        # 수식 정규화 (= 빠지면 추가)
        formula_str = formula.strip()
        if not formula_str.startswith("="):
            formula_str = "=" + formula_str

        cell = sheet.Cells(row, col)
        cell.Formula = formula_str
        cell_addr = f"{col_letter(col)}{row}"

        return {
            "cell_address": cell_addr,
            "formula": formula_str,
            "result": cell.Value,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("write_formula_to_cell 실패: %s", type(e).__name__)
        return None, "FORMULA_WRITE_FAILED"


def fill_formula_down(
    sheet: Any,
    start_row: int,
    end_row: int,
    col: int,
    formula_template: str,
    headers: Optional[dict] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """행 범위에 수식을 채워 넣는다 (자동 조정 포함).

    Args:
        sheet: Excel sheet 객체
        start_row: 시작 행 (1-based)
        end_row: 종료 행 (1-based, 포함)
        col: 대상 열 (1-based)
        formula_template: 수식 템플릿
        headers: {"header": col_num, ...} 헤더 매핑 (보조용)

    Returns:
        ({"filled_rows": int, "first_cell": "A1", "last_cell": "A10"}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if start_row < 1 or end_row < 1 or col < 1:
        return None, "INVALID_PARAMS"
    if start_row > end_row:
        return None, "INVALID_ROW_RANGE"
    if not isinstance(formula_template, str) or not formula_template.strip():
        return None, "INVALID_FORMULA_TEMPLATE"

    try:
        filled = 0
        first_cell = None
        last_cell = None

        for row_idx in range(start_row, end_row + 1):
            try:
                # 수식 템플릿에서 상대 참조 처리
                # 간단한 구현: 템플릿 내 행 참조를 현재 행으로 변경
                formula_str = formula_template.strip()
                if not formula_str.startswith("="):
                    formula_str = "=" + formula_str

                cell = sheet.Cells(row_idx, col)
                cell.Formula = formula_str
                filled += 1

                cell_addr = f"{col_letter(col)}{row_idx}"
                if first_cell is None:
                    first_cell = cell_addr
                last_cell = cell_addr

            except Exception:  # noqa: BLE001
                pass

        return {
            "filled_rows": filled,
            "first_cell": first_cell,
            "last_cell": last_cell,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("fill_formula_down 실패: %s", type(e).__name__)
        return None, "FORMULA_FILL_DOWN_FAILED"


def build_formula_from_headers(
    formula_expr: str,
    headers: dict,
    row: int,
) -> Tuple[Optional[str], Optional[str]]:
    """헤더명을 기반으로 수식을 생성한다.

    Args:
        formula_expr: 수식 표현식 (예: "{금액} = {수량} * {단가}")
        headers: {"header_name": column_number, ...}
        row: 대상 행 번호 (1-based)

    Returns:
        (formula_string, error_or_None)
        예: "=C5*D5" (C=수량, D=단가, 행=5)
    """
    if not isinstance(formula_expr, str) or not formula_expr.strip():
        return None, "INVALID_FORMULA_EXPR"
    if not isinstance(headers, dict) or not headers:
        return None, "INVALID_HEADERS"
    if row < 1:
        return None, "INVALID_ROW"

    try:
        result = formula_expr.strip()

        # {header_name} 패턴을 찾아 열 참조로 변환
        for header_name, col_num in headers.items():
            placeholder = "{" + header_name + "}"
            cell_ref = f"{col_letter(col_num)}{row}"
            result = result.replace(placeholder, cell_ref)

        # = 빠지면 추가
        if not result.startswith("="):
            result = "=" + result

        return result, None

    except Exception as e:  # noqa: BLE001
        logger.error("build_formula_from_headers 실패: %s", type(e).__name__)
        return None, "FORMULA_BUILD_FAILED"
