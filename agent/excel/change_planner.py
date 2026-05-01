"""Excel 변경 계획 수립 (dry-run planning, 절대 실제 수정 없음)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .operation_normalizer import normalize_operation
from .operation_schema import ChangePlan, Operation, OP_EXPORT_PDF_COPY

logger = logging.getLogger(__name__)


def plan_changes(
    sheet: Any,
    operations: list[dict],
) -> tuple[Optional[ChangePlan], Optional[str]]:
    """변경 계획을 수립한다 (dry-run, 실제 수정 없음).

    Args:
        sheet: Excel sheet 객체
        operations: [{"type": str, "sheet": str, "params": dict}, ...]

    Returns:
        (ChangePlan, error_or_None)
    """
    if sheet is None:
        return None, "SHEET_NOT_FOUND"

    if not isinstance(operations, list):
        return None, "INVALID_OPERATIONS_FORMAT"

    if len(operations) == 0:
        return None, "NO_OPERATIONS_PROVIDED"

    try:
        # Operation 정규화
        normalized_ops = []
        for op_dict in operations:
            op, err = normalize_operation(op_dict)
            if err or op is None:
                return None, f"OPERATION_NORMALIZATION_FAILED: {err}"
            normalized_ops.append(op)

        # 위험 요소 분석
        requires_approval = _analyze_approval_requirements(normalized_ops)
        will_modify_original = _analyze_modification_impact(normalized_ops)
        save_mode = _determine_save_mode(normalized_ops, will_modify_original)

        # 경고 수집
        warnings = _collect_warnings(normalized_ops, sheet)

        # 원본 저장 금지 확인
        if will_modify_original and save_mode == "overwrite":
            return None, "ORIGINAL_OVERWRITE_NOT_ALLOWED"

        # 계획 생성
        plan = ChangePlan(
            success=True,
            dry_run=True,
            operations=normalized_ops,
            requires_approval=requires_approval,
            will_modify_original=will_modify_original,
            save_mode=save_mode,
            warnings=warnings if warnings else None,
        )

        return plan, None

    except Exception as e:  # noqa: BLE001
        logger.error("plan_changes failed: %s", type(e).__name__)
        return None, "PLANNING_FAILED"


def _analyze_approval_requirements(operations: list[Operation]) -> bool:
    """승인 필요 여부를 분석한다."""
    high_risk_ops = [op for op in operations if op.risk == "high"]
    write_ops = [
        op for op in operations
        if op.type in ("update_cell_by_header", "insert_row_by_header", "insert_column_by_header")
    ]

    # high risk 작업이 있거나 write 작업이 많으면 승인 필요
    return len(high_risk_ops) > 0 or len(write_ops) > 2


def _analyze_modification_impact(operations: list[Operation]) -> bool:
    """원본 수정 여부를 분석한다."""
    write_ops = [
        op for op in operations
        if op.type in (
            "update_cell_by_header",
            "insert_row_by_header",
            "insert_column_by_header",
            "write_formula_by_header",
            "fill_down_formula",
            "apply_number_format",
            "apply_highlight",
        )
    ]

    return len(write_ops) > 0


def _determine_save_mode(
    operations: list[Operation],
    will_modify_original: bool,
) -> str:
    """저장 모드를 결정한다.

    Returns:
        "copy_only" | "save_as" | "overwrite"
    """
    # 원본을 수정하지 않으면 copy_only
    if not will_modify_original:
        return "copy_only"

    # 원본을 수정하면 save_as만 허용 (overwrite 금지)
    return "save_as"


def _collect_warnings(operations: list[Operation], sheet: Any) -> list[str]:
    """경고 메시지를 수집한다."""
    warnings = []

    for i, op in enumerate(operations):
        # 수식 작업 시 대상 열이 숫자만 있는지 확인
        if op.type == "write_formula_by_header":
            target_header = op.params.get("target_header")
            if target_header:
                warnings.append(
                    f"Op[{i}]: Formula will overwrite existing values in column '{target_header}'"
                )

        # 행 추가 시 헤더 매칭 확인
        if op.type == "insert_row_by_header":
            anchor_header = op.params.get("anchor_header")
            if anchor_header:
                warnings.append(
                    f"Op[{i}]: Will insert row next to '{anchor_header}' anchor"
                )

        # 열 추가 시 방향 확인
        if op.type == "insert_column_by_header":
            position = op.params.get("position", "right")
            anchor_header = op.params.get("anchor_header")
            warnings.append(
                f"Op[{i}]: Will insert column to the {position} of '{anchor_header}'"
            )

        # 요약 시트 생성 시 기존 시트 확인
        if op.type == "create_summary_sheet":
            summary_name = op.params.get("summary_sheet_name")
            warnings.append(
                f"Op[{i}]: Will create new sheet named '{summary_name}'"
            )

    return warnings
