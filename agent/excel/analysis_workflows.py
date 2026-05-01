"""Excel 분석 워크플로우.

표 분석, 데이터 검증, 수식 검증, 보고서 생성을 오케스트레이션한다.
모두 read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from . import (
    data_validator,
    formula_validator,
    header_detector,
    reporter,
    structure_analyzer,
    table_analyzer,
    validator,
)

logger = logging.getLogger(__name__)


def analyze_active_workbook() -> dict:
    """실행 중인 Excel의 활성 시트를 분석한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "analysis": {
                "table_structure": {...} | None,
                "data_quality": {...} | None,
                "formula_errors": {...} | None,
            },
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        # GetActiveObject로 Excel 연결
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

        # 헤더 행 감지
        header_row, err = header_detector.detect_header_row(sheet)
        if err or header_row is None:
            result["error"] = err or "HEADER_DETECTION_FAILED"
            return result

        # 헤더 매핑
        headers, err = header_detector.map_headers(sheet, header_row)
        if err or headers is None:
            result["error"] = err or "HEADER_MAPPING_FAILED"
            return result

        # 표 구조 분석
        table_analysis, err = table_analyzer.analyze_table_structure(
            sheet, header_row, headers
        )

        # 데이터 범위 감지
        data_range, err = table_analyzer.detect_data_range(sheet, header_row)
        if data_range:
            start_row = data_range.get("data_start_row")
            end_row = data_range.get("data_end_row")
            start_col = data_range.get("first_col")
            end_col = data_range.get("last_col")

            # 데이터 품질 검증
            data_quality, err = data_validator.validate_data_range(
                sheet, start_row, end_row, start_col, end_col
            )

            # 수식 에러 스캔
            formula_errors, err = formula_validator.scan_formula_errors(
                sheet, start_row, end_row, start_col, end_col
            )
        else:
            data_quality = None
            formula_errors = None

        result["success"] = True
        result["analysis"] = {
            "table_structure": table_analysis,
            "data_quality": data_quality,
            "formula_errors": formula_errors,
        }
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("analyze_active_workbook 실패: %s", type(e).__name__)
        result["error"] = "ANALYSIS_FAILED"
        return result


def validate_data_quality() -> dict:
    """활성 시트의 데이터 품질을 검증한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "data_quality": {...},
            "issues": [...],
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = "SHEET_ACCESS_FAILED"
            return result

        # 헤더 감지
        header_row, _ = header_detector.detect_header_row(sheet)
        if not header_row:
            header_row = 1

        # 데이터 범위 감지
        data_range, err = table_analyzer.detect_data_range(sheet, header_row)
        if not data_range:
            result["error"] = "DATA_RANGE_DETECTION_FAILED"
            return result

        start_row = data_range.get("data_start_row")
        end_row = data_range.get("data_end_row")
        start_col = data_range.get("first_col")
        end_col = data_range.get("last_col")

        # 품질 검증
        quality, err = data_validator.validate_data_range(
            sheet, start_row, end_row, start_col, end_col
        )

        # 빈 셀 검사
        empty, _ = data_validator.check_empty_cells_in_range(
            sheet, start_row, end_row, start_col, end_col
        )

        issues = []
        if quality and quality.get("error_cells", 0) > 0:
            issues.append({
                "type": "formula_errors",
                "count": quality.get("error_cells", 0),
            })

        result["success"] = True
        result["data_quality"] = quality
        result["empty_cells"] = empty
        result["issues"] = issues
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("validate_data_quality 실패: %s", type(e).__name__)
        result["error"] = "VALIDATION_FAILED"
        return result


def validate_formulas() -> dict:
    """활성 시트의 수식을 검증한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "formula_errors": {...},
            "consistency_issues": [...],
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        app, err = get_active_excel_app()
        if err or app is None:
            result["error"] = _err.EXCEL_APP_NOT_FOUND
            return result

        try:
            wb = app.ActiveWorkbook
            sheet = wb.ActiveSheet
            if sheet is None:
                result["error"] = _err.SHEET_NOT_FOUND
                return result
            result["sheet"] = str(sheet.Name)
        except Exception:  # noqa: BLE001
            result["error"] = "SHEET_ACCESS_FAILED"
            return result

        # 헤더 감지
        header_row, _ = header_detector.detect_header_row(sheet)
        if not header_row:
            header_row = 1

        # 데이터 범위 감지
        data_range, err = table_analyzer.detect_data_range(sheet, header_row)
        if not data_range:
            result["error"] = "DATA_RANGE_DETECTION_FAILED"
            return result

        start_row = data_range.get("data_start_row")
        end_row = data_range.get("data_end_row")
        start_col = data_range.get("first_col")
        end_col = data_range.get("last_col")

        # 수식 에러 스캔
        errors, err = formula_validator.scan_formula_errors(
            sheet, start_row, end_row, start_col, end_col
        )

        # 일관성 검사
        consistency_issues = []
        for col_idx in range(start_col, min(end_col + 1, 50)):
            consistency, _ = formula_validator.check_formula_consistency_in_range(
                sheet, start_row, end_row, col_idx
            )
            if consistency and not consistency.get("all_consistent"):
                consistency_issues.append({
                    "col": col_idx,
                    "inconsistent_rows": consistency.get("inconsistent_rows", []),
                })

        result["success"] = True
        result["formula_errors"] = errors
        result["consistency_issues"] = consistency_issues
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("validate_formulas 실패: %s", type(e).__name__)
        result["error"] = "FORMULA_VALIDATION_FAILED"
        return result


def generate_analysis_report() -> dict:
    """활성 시트의 종합 분석 보고서를 생성한다.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "report": {
                "summary": {...},
                "issues": [...],
                "recommendations": [...],
            },
            "report_text": str,
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        # 전체 분석 수행
        analysis = analyze_active_workbook()
        if not analysis.get("success"):
            result["error"] = analysis.get("error", "ANALYSIS_FAILED")
            return result

        sheet_name = analysis.get("sheet")
        analysis_data = analysis.get("analysis", {})

        # 보고서 생성
        report = reporter.build_analysis_report(
            sheet_name=sheet_name,
            table_analysis=analysis_data.get("table_structure"),
            data_validation=analysis_data.get("data_quality"),
            formula_errors=analysis_data.get("formula_errors"),
        )

        # 텍스트 형식 보고서
        report_text = reporter.format_report_as_text(report)

        result["success"] = True
        result["sheet"] = sheet_name
        result["report"] = report
        result["report_text"] = report_text
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("generate_analysis_report 실패: %s", type(e).__name__)
        result["error"] = "REPORT_GENERATION_FAILED"
        return result


def analyze_active_sheet_structure() -> dict:
    """활성 시트의 상세 구조를 분석한다 (EXCEL-PC-4A 고도화).

    병합셀, 숨김행/열, AutoFilter, 표 영역, 헤더/합계 행, 수식, 숫자텍스트 감지.

    Returns:
        {
            "success": bool,
            "sheet_name": str | None,
            "structure": {...},
            "error": str | None,
        }
    """
    result = validator.build_update_result()

    try:
        from .connectors.excel_com_connector import get_active_excel_app
        from . import errors as _err

        # GetActiveObject로 Excel 연결
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

        # 상세 구조 분석
        structure_info, err = structure_analyzer.analyze_active_sheet_structure(sheet)
        if err or structure_info is None:
            result["error"] = err or "STRUCTURE_ANALYSIS_FAILED"
            return result

        result["success"] = True
        result["structure"] = structure_info
        return result

    except Exception as e:  # noqa: BLE001
        logger.error("analyze_active_sheet_structure 실패: %s", type(e).__name__)
        result["error"] = "STRUCTURE_ANALYSIS_FAILED"
        return result
