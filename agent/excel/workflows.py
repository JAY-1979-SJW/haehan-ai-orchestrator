"""Excel 모듈화 워크플로우.

헤더 기반 행/열 추가, 수식 입력을 통합 오케스트레이션한다.
각 워크플로우는:
1. active workbook/sheet 연결
2. header_detector로 header map 확보
3. row_finder/column_writer로 위치 계산
4. row_writer/column_writer/formula_writer 실행
5. copy_saver.save_copy()
6. validator.build_update_result()
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import (
    cell_writer,
    column_writer,
    copy_saver,
    formula_writer,
    header_detector,
    row_finder,
    row_writer,
    style_copier,
    validator,
)

logger = logging.getLogger(__name__)


def insert_row_by_header_copy(
    row_match_header: str,
    row_match_value: Any,
    position: str = "below",
    values: Optional[dict] = None,
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """헤더 기준으로 행을 찾아, 그 행 위/아래에 새 행을 추가하고 값을 입력한다.

    Args:
        row_match_header: 행 식별용 헤더명
        row_match_value: 행 식별용 셀값
        position: "below" | "above"
        values: {"header_name": value, ...} (선택사항)
        output_path: 복사본 저장 경로 (선택사항)
        approval_token: 승인 토큰
        allow_write: 쓰기 허용 여부

    Returns:
        {
            "success": bool,
            "new_row": int | None,
            "filled_cells": [...] | None,
            "output_file": str | None,
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    # approval 검증 (connector의 _require_approval_for_write와 동일)
    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        result["error"] = "WRITE_APPROVAL_REQUIRED"
        return result

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        # GetActiveObject로 Excel 연결
        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        # ActiveWorkbook 확인
        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error"] = "NO_ACTIVE_WORKBOOK"
            return result

        # ActiveSheet 확인
        try:
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        # 헤더 행 자동 인식
        header_row, err = header_detector.detect_header_row(sheet)
        if err or header_row is None:
            result["error"] = err or "HEADER_DETECTION_FAILED"
            return result
        result["header_row"] = header_row

        # 헤더 매핑
        headers, err = header_detector.map_headers(sheet, header_row)
        if err or headers is None:
            result["error"] = err or "HEADER_MAPPING_FAILED"
            return result

        # row_match_header 열 번호 확인
        if row_match_header not in headers:
            result["error"] = f"HEADER_NOT_FOUND: {row_match_header}"
            return result
        match_col = headers[row_match_header]

        # 행 찾기
        matched_row, err = row_finder.find_row_by_header_value(
            sheet, header_row, match_col, row_match_value,
        )
        if err or matched_row is None:
            result["error"] = err or f"ROW_NOT_FOUND: {row_match_value}"
            return result
        result["matched_row"] = matched_row

        # 새 행 삽입
        insert_pos = matched_row + 1 if position == "below" else matched_row
        insert_result, err = row_writer.insert_row_at(
            sheet, insert_pos, copy_format_from=matched_row,
        )
        if err or insert_result is None:
            result["error"] = err or "ROW_INSERT_FAILED"
            return result

        new_row = insert_result.get("inserted_row")
        result["new_row"] = new_row

        # 값 입력
        if values:
            fill_result, err = row_writer.fill_row_by_headers(
                sheet, new_row, values, headers,
            )
            if err:
                result["error"] = err
                return result
            result["filled_cells"] = fill_result.get("filled_cells", [])

        # 복사본 저장
        copy_path, err = copy_saver.build_safe_copy_path(wb, output_path)
        if err or copy_path is None:
            result["error"] = err or "COPY_PATH_BUILD_FAILED"
            return result

        save_err = copy_saver.save_copy(wb, copy_path)
        if save_err:
            result["error"] = save_err
            return result

        result["success"] = True
        result["output_file"] = copy_path
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("insert_row_by_header_copy 실패: %s", type(e).__name__)
        result["error"] = "INSERT_ROW_WORKFLOW_FAILED"
        return result


def insert_column_by_header_copy(
    anchor_header: str,
    new_header: str,
    position: str = "right",
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """헤더 기준으로 열을 추가한다.

    Args:
        anchor_header: 기준 헤더명
        new_header: 새 헤더명
        position: "right" | "left"
        output_path: 복사본 저장 경로
        approval_token: 승인 토큰
        allow_write: 쓰기 허용 여부

    Returns:
        {
            "success": bool,
            "new_col": int | None,
            "output_file": str | None,
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        result["error"] = "WRITE_APPROVAL_REQUIRED"
        return result

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error"] = "NO_ACTIVE_WORKBOOK"
            return result

        try:
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        header_row, err = header_detector.detect_header_row(sheet)
        if err or header_row is None:
            result["error"] = err or "HEADER_DETECTION_FAILED"
            return result
        result["header_row"] = header_row

        headers, err = header_detector.map_headers(sheet, header_row)
        if err or headers is None:
            result["error"] = err or "HEADER_MAPPING_FAILED"
            return result

        if anchor_header not in headers:
            result["error"] = f"HEADER_NOT_FOUND: {anchor_header}"
            return result
        anchor_col = headers[anchor_header]

        # 열 추가
        insert_result, err = column_writer.insert_column_next_to_header(
            sheet, header_row, anchor_header, anchor_col, new_header, position,
        )
        if err or insert_result is None:
            result["error"] = err or "COLUMN_INSERT_FAILED"
            return result

        new_col = insert_result
        result["new_col"] = new_col

        # 복사본 저장
        copy_path, err = copy_saver.build_safe_copy_path(wb, output_path)
        if err or copy_path is None:
            result["error"] = err or "COPY_PATH_BUILD_FAILED"
            return result

        save_err = copy_saver.save_copy(wb, copy_path)
        if save_err:
            result["error"] = save_err
            return result

        result["success"] = True
        result["output_file"] = copy_path
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("insert_column_by_header_copy 실패: %s", type(e).__name__)
        result["error"] = "INSERT_COLUMN_WORKFLOW_FAILED"
        return result


def write_formula_by_header_copy(
    target_header: str,
    formula: str,
    start_row: Optional[int] = None,
    end_row: Optional[int] = None,
    output_path: Optional[str] = None,
    *,
    approval_token: Optional[str] = None,
    allow_write: bool = False,
) -> dict:
    """헤더 기준으로 셀/열에 수식을 입력한다.

    Args:
        target_header: 대상 헤더명
        formula: 수식 (예: "=A1+B1" 또는 "{수량}*{단가}")
        start_row: 시작 행 (None이면 header_row + 1)
        end_row: 종료 행 (None이면 첫 행만)
        output_path: 복사본 저장 경로
        approval_token: 승인 토큰
        allow_write: 쓰기 허용 여부

    Returns:
        {
            "success": bool,
            "filled_rows": int | None,
            "output_file": str | None,
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    if not approval_token or not isinstance(approval_token, str) or not approval_token.strip():
        result["error"] = "WRITE_APPROVAL_REQUIRED"
        return result

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            if wb is None:
                result["error"] = "NO_ACTIVE_WORKBOOK"
                return result
        except Exception:  # noqa: BLE001
            result["error"] = "NO_ACTIVE_WORKBOOK"
            return result

        try:
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = _err.SHEET_NOT_FOUND
            return result

        header_row, err = header_detector.detect_header_row(sheet)
        if err or header_row is None:
            result["error"] = err or "HEADER_DETECTION_FAILED"
            return result
        result["header_row"] = header_row

        headers, err = header_detector.map_headers(sheet, header_row)
        if err or headers is None:
            result["error"] = err or "HEADER_MAPPING_FAILED"
            return result

        if target_header not in headers:
            result["error"] = f"HEADER_NOT_FOUND: {target_header}"
            return result
        target_col = headers[target_header]

        # 수식 입력
        s_row = start_row if start_row and start_row > header_row else header_row + 1
        e_row = end_row if end_row and end_row >= s_row else s_row

        fill_result, err = formula_writer.fill_formula_down(
            sheet, s_row, e_row, target_col, formula, headers,
        )
        if err or fill_result is None:
            result["error"] = err or "FORMULA_WRITE_FAILED"
            return result

        result["filled_rows"] = fill_result.get("filled_rows", 0)

        # 복사본 저장
        copy_path, err = copy_saver.build_safe_copy_path(wb, output_path)
        if err or copy_path is None:
            result["error"] = err or "COPY_PATH_BUILD_FAILED"
            return result

        save_err = copy_saver.save_copy(wb, copy_path)
        if save_err:
            result["error"] = save_err
            return result

        result["success"] = True
        result["output_file"] = copy_path
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("write_formula_by_header_copy 실패: %s", type(e).__name__)
        result["error"] = "WRITE_FORMULA_WORKFLOW_FAILED"
        return result
