"""Operation 정규화 및 검증."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .operation_schema import (
    Operation,
    OP_UPDATE_CELL,
    OP_INSERT_ROW,
    OP_INSERT_COLUMN,
    OP_WRITE_FORMULA,
    OP_FILL_DOWN_FORMULA,
    OP_COPY_STYLE,
    OP_APPLY_NUMBER_FORMAT,
    OP_APPLY_HIGHLIGHT,
    OP_CREATE_SUMMARY_SHEET,
    OP_EXPORT_PDF_COPY,
    RISK_LOW,
    RISK_MEDIUM,
)

logger = logging.getLogger(__name__)


def normalize_operation(op_dict: dict) -> tuple[Optional[Operation], Optional[str]]:
    """Operation dict를 정규화하고 검증한다.

    Args:
        op_dict: {"type": str, "sheet": str, "params": dict, ...}

    Returns:
        (Operation, error_or_None)
    """
    if not isinstance(op_dict, dict):
        return None, "INVALID_OPERATION_FORMAT"

    op_type = op_dict.get("type", "").strip()
    sheet = op_dict.get("sheet", "").strip()
    params = op_dict.get("params", {})

    if not op_type or not sheet or not isinstance(params, dict):
        return None, "MISSING_REQUIRED_FIELDS"

    # 타입별 검증
    if op_type == OP_UPDATE_CELL:
        normalized, err = _normalize_update_cell(params)
    elif op_type == OP_INSERT_ROW:
        normalized, err = _normalize_insert_row(params)
    elif op_type == OP_INSERT_COLUMN:
        normalized, err = _normalize_insert_column(params)
    elif op_type == OP_WRITE_FORMULA:
        normalized, err = _normalize_write_formula(params)
    elif op_type == OP_FILL_DOWN_FORMULA:
        normalized, err = _normalize_fill_down_formula(params)
    elif op_type == OP_COPY_STYLE:
        normalized, err = _normalize_copy_style(params)
    elif op_type == OP_APPLY_NUMBER_FORMAT:
        normalized, err = _normalize_apply_number_format(params)
    elif op_type == OP_APPLY_HIGHLIGHT:
        normalized, err = _normalize_apply_highlight(params)
    elif op_type == OP_CREATE_SUMMARY_SHEET:
        normalized, err = _normalize_create_summary_sheet(params)
    elif op_type == OP_EXPORT_PDF_COPY:
        normalized, err = _normalize_export_pdf_copy(params)
    else:
        return None, "UNKNOWN_OPERATION_TYPE"

    if err or normalized is None:
        return None, err

    try:
        operation = Operation(
            type=op_type,
            sheet=sheet,
            risk=normalized.get("risk", RISK_MEDIUM),
            params=normalized,
        )
        return operation, None
    except Exception as e:  # noqa: BLE001
        logger.error("normalize_operation failed: %s", type(e).__name__)
        return None, "OPERATION_CREATION_FAILED"


def _normalize_update_cell(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """update_cell_by_header 파라미터 검증."""
    required = ["row_match_header", "row_match_value", "target_header", "new_value"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_MEDIUM,
        "row_match_header": str(params["row_match_header"]),
        "row_match_value": params["row_match_value"],
        "target_header": str(params["target_header"]),
        "new_value": params["new_value"],
        "old_value": params.get("old_value"),
    }, None


def _normalize_insert_row(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """insert_row_by_header 파라미터 검증."""
    required = ["anchor_header", "anchor_value", "new_row_data"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_MEDIUM,
        "anchor_header": str(params["anchor_header"]),
        "anchor_value": params["anchor_value"],
        "new_row_data": dict(params["new_row_data"]),
    }, None


def _normalize_insert_column(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """insert_column_by_header 파라미터 검증."""
    required = ["anchor_header", "new_header"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_MEDIUM,
        "anchor_header": str(params["anchor_header"]),
        "new_header": str(params["new_header"]),
        "position": str(params.get("position", "right")),
    }, None


def _normalize_write_formula(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """write_formula_by_header 파라미터 검증."""
    required = ["target_header", "formula"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    formula = str(params["formula"])
    if not formula.startswith("="):
        formula = "=" + formula

    return {
        "risk": RISK_MEDIUM,
        "target_header": str(params["target_header"]),
        "formula": formula,
        "start_row": params.get("start_row"),
        "end_row": params.get("end_row"),
    }, None


def _normalize_fill_down_formula(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """fill_down_formula 파라미터 검증."""
    required = ["target_header", "source_row"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_MEDIUM,
        "target_header": str(params["target_header"]),
        "source_row": int(params["source_row"]),
        "target_range": params.get("target_range"),
    }, None


def _normalize_copy_style(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """copy_style 파라미터 검증."""
    required = ["source_header", "target_header"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_LOW,
        "source_header": str(params["source_header"]),
        "target_header": str(params["target_header"]),
    }, None


def _normalize_apply_number_format(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """apply_number_format 파라미터 검증."""
    required = ["target_header", "format_code"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_LOW,
        "target_header": str(params["target_header"]),
        "format_code": str(params["format_code"]),
    }, None


def _normalize_apply_highlight(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """apply_highlight 파라미터 검증."""
    required = ["target_header", "color"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_LOW,
        "target_header": str(params["target_header"]),
        "color": str(params["color"]),
    }, None


def _normalize_create_summary_sheet(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """create_summary_sheet 파라미터 검증."""
    required = ["source_sheet", "summary_sheet_name"]
    if not all(k in params for k in required):
        return None, "MISSING_REQUIRED_PARAMS"

    return {
        "risk": RISK_MEDIUM,
        "source_sheet": str(params["source_sheet"]),
        "summary_sheet_name": str(params["summary_sheet_name"]),
        "summary_type": str(params.get("summary_type", "pivot")),
    }, None


def _normalize_export_pdf_copy(params: dict) -> tuple[Optional[dict], Optional[str]]:
    """export_pdf_copy 파라미터 검증."""
    return {
        "risk": RISK_LOW,
        "output_path": params.get("output_path"),
    }, None
