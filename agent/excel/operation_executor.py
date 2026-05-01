"""Operation 개별 실행."""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from .operation_schema import Operation

logger = logging.getLogger(__name__)


def execute_operation(
    sheet: Any,
    operation: Operation,
) -> Tuple[bool, Optional[str], dict]:
    """단일 operation을 실행한다.

    Args:
        sheet: Excel sheet 객체
        operation: Operation 인스턴스

    Returns:
        (success: bool, error: Optional[str], details: dict)
    """
    if sheet is None:
        return False, "SHEET_NOT_FOUND", {}

    if not isinstance(operation, Operation):
        return False, "INVALID_OPERATION", {}

    try:
        op_type = operation.type
        params = operation.params

        if op_type == "update_cell_by_header":
            return _execute_update_cell(sheet, params)
        elif op_type == "insert_row_by_header":
            return _execute_insert_row(sheet, params)
        elif op_type == "insert_column_by_header":
            return _execute_insert_column(sheet, params)
        elif op_type == "write_formula_by_header":
            return _execute_write_formula(sheet, params)
        elif op_type == "fill_down_formula":
            return _execute_fill_down_formula(sheet, params)
        elif op_type == "copy_style":
            return _execute_copy_style(sheet, params)
        elif op_type == "apply_number_format":
            return _execute_apply_number_format(sheet, params)
        elif op_type == "apply_highlight":
            return _execute_apply_highlight(sheet, params)
        elif op_type == "create_summary_sheet":
            return _execute_create_summary_sheet(sheet, params)
        elif op_type == "export_pdf_copy":
            return _execute_export_pdf_copy(sheet, params)
        else:
            return False, "UNKNOWN_OPERATION_TYPE", {}

    except Exception as e:  # noqa: BLE001
        logger.error("execute_operation failed: %s", type(e).__name__)
        return False, f"EXECUTION_FAILED: {type(e).__name__}", {}


def _execute_update_cell(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """update_cell_by_header 실행."""
    try:
        # Stub: 실제 구현은 향후 추가
        old_value = params.get("old_value")
        new_value = params.get("new_value")

        return True, None, {
            "old_value": old_value,
            "new_value": new_value,
            "updated": True,
        }

    except Exception as e:  # noqa: BLE001
        logger.error("_execute_update_cell failed: %s", type(e).__name__)
        return False, "UPDATE_CELL_FAILED", {}


def _execute_insert_row(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """insert_row_by_header 실행 (stub)."""
    try:
        # 실제 구현은 복잡하므로 여기서는 stub
        return True, None, {"row_inserted": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_insert_row failed: %s", type(e).__name__)
        return False, "INSERT_ROW_FAILED", {}


def _execute_insert_column(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """insert_column_by_header 실행 (stub)."""
    try:
        return True, None, {"column_inserted": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_insert_column failed: %s", type(e).__name__)
        return False, "INSERT_COLUMN_FAILED", {}


def _execute_write_formula(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """write_formula_by_header 실행 (stub)."""
    try:
        return True, None, {"formula_written": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_write_formula failed: %s", type(e).__name__)
        return False, "WRITE_FORMULA_FAILED", {}


def _execute_fill_down_formula(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """fill_down_formula 실행 (stub)."""
    try:
        return True, None, {"formula_filled": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_fill_down_formula failed: %s", type(e).__name__)
        return False, "FILL_DOWN_FORMULA_FAILED", {}


def _execute_copy_style(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """copy_style 실행 (stub)."""
    try:
        return True, None, {"style_copied": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_copy_style failed: %s", type(e).__name__)
        return False, "COPY_STYLE_FAILED", {}


def _execute_apply_number_format(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """apply_number_format 실행 (stub)."""
    try:
        return True, None, {"format_applied": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_apply_number_format failed: %s", type(e).__name__)
        return False, "APPLY_FORMAT_FAILED", {}


def _execute_apply_highlight(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """apply_highlight 실행 (stub)."""
    try:
        return True, None, {"highlight_applied": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_apply_highlight failed: %s", type(e).__name__)
        return False, "APPLY_HIGHLIGHT_FAILED", {}


def _execute_create_summary_sheet(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """create_summary_sheet 실행 (stub)."""
    try:
        return True, None, {"summary_sheet_created": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_create_summary_sheet failed: %s", type(e).__name__)
        return False, "CREATE_SUMMARY_FAILED", {}


def _execute_export_pdf_copy(sheet: Any, params: dict) -> Tuple[bool, Optional[str], dict]:
    """export_pdf_copy 실행 (stub)."""
    try:
        return True, None, {"pdf_exported": True}
    except Exception as e:  # noqa: BLE001
        logger.error("_execute_export_pdf_copy failed: %s", type(e).__name__)
        return False, "EXPORT_PDF_FAILED", {}
