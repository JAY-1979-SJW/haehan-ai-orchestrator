"""Excel 헤더 행 자동 인식.

헤더 행을 상위 max_scan_rows 내에서 자동으로 감지하고,
헤더명을 열 번호로 매핑한다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def detect_header_row(
    sheet: Any,
    max_scan_rows: int = 20,
    max_columns: int = 50,
) -> Tuple[Optional[int], Optional[str]]:
    """시트의 상위 max_scan_rows 행을 스캔해 헤더 행 자동 인식.

    헤더 판정 기준:
    - 문자열 셀 비율 (높을수록 헤더일 가능성 높음)
    - 일반적 헤더명 포함도
    - 간격 있는 헤더도 인식 (B4, D4, F4 등)

    반환: (header_row, error_or_None)
      header_row는 1-based (Excel 행 번호)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    try:
        # 각 행의 점수 계산
        scores: list[tuple[int, float]] = []
        common_headers = {
            "품명", "명칭", "자재명", "규격", "수량", "단위", "단가", "금액",
            "비고", "설명", "이름", "코드", "번호", "날짜", "금액", "가격",
            "기관코드", "사업분야코드", "사업종류코드", "준공구분", "노선코드",
            "수행주기구분", "승인상태", "안전관리비", "수행단계",
        }

        for row_idx in range(1, max_scan_rows + 1):
            non_empty_count = 0
            string_count = 0
            header_match_count = 0
            numeric_count = 0

            for col_idx in range(1, max_columns + 1):
                try:
                    cell = sheet.Cells(row_idx, col_idx)
                    value = cell.Value

                    if value is not None:
                        non_empty_count += 1
                        if isinstance(value, str):
                            string_count += 1
                            if value.strip() in common_headers:
                                header_match_count += 1
                        elif isinstance(value, (int, float)):
                            numeric_count += 1
                except Exception:  # noqa: BLE001
                    pass

            if non_empty_count == 0:
                continue

            string_ratio = (string_count / non_empty_count) if non_empty_count > 0 else 0
            score = (string_ratio * 50) + (header_match_count * 10) - (numeric_count * 2)
            scores.append((row_idx, score))

        if not scores:
            return None, "NO_HEADER_ROW_FOUND"

        header_row = max(scores, key=lambda x: x[1])[0]
        return header_row, None

    except Exception as e:  # noqa: BLE001
        logger.debug("detect_header_row 실패: %s", type(e).__name__)
        return None, "HEADER_DETECTION_FAILED"


def map_headers(
    sheet: Any,
    header_row: int,
    max_columns: int = 50,
) -> Tuple[Optional[dict], Optional[str]]:
    """헤더 행의 셀값을 header_name → column_number로 매핑.

    반환: ({"header_name": column_number, ...}, error_or_None)
      column_number는 1-based (Excel 열 번호)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"
    if header_row < 1:
        return None, "INVALID_HEADER_ROW"

    try:
        headers: dict = {}
        for col_idx in range(1, max_columns + 1):
            try:
                cell = sheet.Cells(header_row, col_idx)
                value = cell.Value
                if value is not None:
                    header_name = str(value).strip()
                    if header_name:
                        headers[header_name] = col_idx
            except Exception:  # noqa: BLE001
                pass

        if not headers:
            return None, "NO_HEADERS_IN_ROW"

        return headers, None

    except Exception as e:  # noqa: BLE001
        logger.debug("map_headers 실패: %s", type(e).__name__)
        return None, "HEADER_MAPPING_FAILED"
