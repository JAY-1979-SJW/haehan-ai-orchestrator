"""Excel 표 구조 분석.

헤더 행, 데이터 범위, 열 타입, 경계 감지를 수행한다.
Read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def analyze_column_type(
    sheet: Any,
    col_num: int,
    header_row: int,
    data_start_row: int,
    max_rows: int = 100,
) -> Tuple[Optional[dict], Optional[str]]:
    """열의 데이터 타입을 분석한다.

    Args:
        sheet: Excel sheet 객체
        col_num: 열 번호 (1-based)
        header_row: 헤더 행 번호
        data_start_row: 데이터 시작 행
        max_rows: 분석 행 수 (성능 고려)

    Returns:
        ({"type": "string|number|date|formula", "count": int, "empty": int}, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if col_num < 1 or header_row < 1 or data_start_row < 1:
        return None, "INVALID_PARAMS"

    try:
        type_counts = {
            "string": 0,
            "number": 0,
            "date": 0,
            "formula": 0,
            "empty": 0,
            "other": 0,
        }

        for row_idx in range(data_start_row, min(data_start_row + max_rows, 1000)):
            try:
                cell = sheet.Cells(row_idx, col_num)
                value = cell.Value

                if value is None:
                    type_counts["empty"] += 1
                    continue

                # 수식 확인
                try:
                    formula = cell.Formula
                    if isinstance(formula, str) and formula.startswith("="):
                        type_counts["formula"] += 1
                        continue
                except Exception:  # noqa: BLE001
                    pass

                # 타입 추론
                if isinstance(value, (int, float)):
                    type_counts["number"] += 1
                elif isinstance(value, str):
                    # 날짜 형식인지 추론 (간단한 휴리스틱)
                    if _looks_like_date(value):
                        type_counts["date"] += 1
                    else:
                        type_counts["string"] += 1
                else:
                    type_counts["other"] += 1

            except Exception:  # noqa: BLE001
                type_counts["other"] += 1

        # 주요 타입 결정
        dominant_type = max(
            (k, v) for k, v in type_counts.items() if k != "empty"
        )[0]

        return {
            "type": dominant_type,
            "type_breakdown": type_counts,
            "total_non_empty": sum(v for k, v in type_counts.items() if k != "empty"),
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("analyze_column_type 실패: %s", type(e).__name__)
        return None, "COLUMN_ANALYSIS_FAILED"


def _looks_like_date(value: str) -> bool:
    """문자열이 날짜처럼 보이는지 휴리스틱으로 판정."""
    if not isinstance(value, str):
        return False
    s = value.strip().lower()
    date_patterns = [
        "-",  # YYYY-MM-DD
        "/",  # MM/DD/YYYY
        ".",  # DD.MM.YYYY
    ]
    return any(pat in s for pat in date_patterns) and len(s) >= 8


def detect_data_range(
    sheet: Any,
    header_row: int,
    max_scan_rows: int = 1000,
) -> Tuple[Optional[dict], Optional[str]]:
    """표의 데이터 범위를 감지한다.

    Args:
        sheet: Excel sheet 객체
        header_row: 헤더 행 번호 (1-based)
        max_scan_rows: 최대 스캔 행 수

    Returns:
        ({
            "header_row": int,
            "data_start_row": int,
            "data_end_row": int,
            "first_col": int,
            "last_col": int,
            "row_count": int,
            "col_count": int,
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1:
        return None, "INVALID_HEADER_ROW"

    try:
        # UsedRange 확인
        try:
            used_range = sheet.UsedRange
            used_first_row = used_range.Row
            used_last_row = used_first_row + used_range.Rows.Count - 1
            used_first_col = used_range.Column
            used_last_col = used_first_col + used_range.Columns.Count - 1
        except Exception:  # noqa: BLE001
            # fallback: 직접 스캔
            used_first_row = header_row
            used_first_col = 1
            used_last_row = header_row + max_scan_rows
            used_last_col = 50

        # 데이터 시작 행 결정 (헤더 다음 행)
        data_start = header_row + 1

        # 데이터 종료 행 결정 (마지막 비어있지 않은 행)
        data_end = header_row
        for row_idx in range(data_start, min(used_last_row + 1, 1000)):
            try:
                # 행이 완전히 비어있는지 확인
                has_content = False
                for col_idx in range(used_first_col, min(used_last_col + 1, 50)):
                    try:
                        cell = sheet.Cells(row_idx, col_idx)
                        if cell.Value is not None:
                            has_content = True
                            break
                    except Exception:  # noqa: BLE001
                        pass
                if has_content:
                    data_end = row_idx
                elif data_end > header_row:
                    # 내용이 있다가 비어있으면 끝
                    break
            except Exception:  # noqa: BLE001
                break

        # 첫/마지막 열 결정
        first_col = used_first_col
        last_col = used_first_col

        # 헤더 행에서 마지막 열 찾기
        for col_idx in range(used_first_col, min(used_last_col + 1, 50)):
            try:
                cell = sheet.Cells(header_row, col_idx)
                if cell.Value is not None:
                    last_col = col_idx
            except Exception:  # noqa: BLE001
                pass

        row_count = max(1, data_end - data_start + 1)
        col_count = last_col - first_col + 1

        return {
            "header_row": header_row,
            "data_start_row": data_start,
            "data_end_row": data_end,
            "first_col": first_col,
            "last_col": last_col,
            "row_count": row_count,
            "col_count": col_count,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("detect_data_range 실패: %s", type(e).__name__)
        return None, "DATA_RANGE_DETECTION_FAILED"


def analyze_table_structure(
    sheet: Any,
    header_row: int,
    headers: dict,
) -> Tuple[Optional[dict], Optional[str]]:
    """표 전체의 구조를 분석한다.

    Args:
        sheet: Excel sheet 객체
        header_row: 헤더 행 번호
        headers: {"header_name": column_number, ...}

    Returns:
        ({
            "header_row": int,
            "columns": [{
                "name": str,
                "col_num": int,
                "type": str,
                "empty_count": int,
            }, ...],
            "data_range": {...},
            "summary": {...},
        }, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1 or not isinstance(headers, dict):
        return None, "INVALID_PARAMS"

    try:
        # 데이터 범위 감지
        range_result, err = detect_data_range(sheet, header_row)
        if err or range_result is None:
            return None, err or "DATA_RANGE_DETECTION_FAILED"

        columns = []
        for header_name, col_num in sorted(
            headers.items(), key=lambda x: x[1]
        ):
            col_result, err = analyze_column_type(
                sheet, col_num, header_row,
                range_result["data_start_row"],
            )
            if col_result:
                columns.append({
                    "name": header_name,
                    "col_num": col_num,
                    "type": col_result.get("type"),
                    "breakdown": col_result.get("type_breakdown"),
                    "non_empty_count": col_result.get("total_non_empty"),
                })
            else:
                columns.append({
                    "name": header_name,
                    "col_num": col_num,
                    "type": "unknown",
                    "error": err,
                })

        return {
            "header_row": header_row,
            "data_range": range_result,
            "columns": columns,
            "summary": {
                "header_count": len(headers),
                "data_row_count": range_result["row_count"],
                "col_count": range_result["col_count"],
            },
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("analyze_table_structure 실패: %s", type(e).__name__)
        return None, "TABLE_ANALYSIS_FAILED"
