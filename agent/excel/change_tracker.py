"""Excel 변경 추적.

변경 전후 분석 결과를 비교하여 무엇이 변경되었는지 추적한다.
Read-only 작업이므로 원본 수정 없음.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def compare_analyses(
    before_analysis: dict,
    after_analysis: dict,
) -> Tuple[Optional[dict], Optional[str]]:
    """변경 전후 분석을 비교한다.

    Args:
        before_analysis: 변경 전 분석 결과 (analyze_active_workbook 반환값)
        after_analysis: 변경 후 분석 결과

    Returns:
        ({
            "table_structure_changed": bool,
            "data_quality_changed": bool,
            "formula_errors_changed": bool,
            "details": {...},
        }, error_or_None)
    """
    if not isinstance(before_analysis, dict) or not isinstance(after_analysis, dict):
        return None, "INVALID_ANALYSIS_DATA"

    try:
        before_data = before_analysis.get("analysis", {})
        after_data = after_analysis.get("analysis", {})

        table_before = before_data.get("table_structure") or {}
        table_after = after_data.get("table_structure") or {}

        quality_before = before_data.get("data_quality") or {}
        quality_after = after_data.get("data_quality") or {}

        errors_before = before_data.get("formula_errors") or {}
        errors_after = after_data.get("formula_errors") or {}

        # 테이블 구조 변경 감지
        table_changed = _compare_dicts(
            table_before.get("summary", {}),
            table_after.get("summary", {}),
        )

        # 데이터 품질 변경 감지
        quality_changed = _compare_dicts(
            {k: v for k, v in quality_before.items() if k in ["quality_score", "error_cells"]},
            {k: v for k, v in quality_after.items() if k in ["quality_score", "error_cells"]},
        )

        # 수식 에러 변경 감지
        errors_changed = _compare_dicts(
            {k: v for k, v in errors_before.items() if k in ["error_count", "error_types"]},
            {k: v for k, v in errors_after.items() if k in ["error_count", "error_types"]},
        )

        return {
            "table_structure_changed": table_changed,
            "data_quality_changed": quality_changed,
            "formula_errors_changed": errors_changed,
            "before_summary": table_before.get("summary", {}),
            "after_summary": table_after.get("summary", {}),
            "quality_before": quality_before.get("quality_score"),
            "quality_after": quality_after.get("quality_score"),
            "errors_before": errors_before.get("error_count", 0),
            "errors_after": errors_after.get("error_count", 0),
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("compare_analyses 실패: %s", type(e).__name__)
        return None, "COMPARISON_FAILED"


def _compare_dicts(before: dict, after: dict) -> bool:
    """두 딕셔너리를 비교하여 변경이 있는지 확인한다."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False

    # 키의 개수가 다르면 변경
    if len(before) != len(after):
        return True

    # 같은 키의 값이 다르면 변경
    for key in before:
        if key not in after or before[key] != after[key]:
            return True

    return False


def track_cell_changes(
    sheet_before: Any,
    sheet_after: Any,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """두 시트의 셀 값을 비교하여 변경된 셀을 추적한다.

    Args:
        sheet_before: 변경 전 시트
        sheet_after: 변경 후 시트
        start_row, end_row, start_col, end_col: 범위

    Returns:
        ({
            "changed_cells": [{
                "cell": "A1",
                "before": ...,
                "after": ...,
            }, ...],
            "change_count": int,
        }, error_or_None)
    """
    if sheet_before is None or sheet_after is None:
        return None, "SHEET_NOT_FOUND"
    if start_row < 1 or start_col < 1:
        return None, "INVALID_PARAMS"

    try:
        from .cell_writer import col_letter

        changed_cells = []

        for row_idx in range(start_row, min(end_row + 1, 1000)):
            for col_idx in range(start_col, min(end_col + 1, 50)):
                try:
                    before_cell = sheet_before.Cells(row_idx, col_idx)
                    after_cell = sheet_after.Cells(row_idx, col_idx)

                    before_value = before_cell.Value
                    after_value = after_cell.Value

                    if before_value != after_value:
                        cell_addr = f"{col_letter(col_idx)}{row_idx}"
                        changed_cells.append({
                            "cell": cell_addr,
                            "before": before_value,
                            "after": after_value,
                        })
                except Exception:  # noqa: BLE001
                    pass

        return {
            "changed_cells": changed_cells,
            "change_count": len(changed_cells),
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("track_cell_changes 실패: %s", type(e).__name__)
        return None, "CHANGE_TRACKING_FAILED"


def generate_change_summary(
    before_analysis: dict,
    after_analysis: dict,
    changed_cells: Optional[list] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """변경 요약을 생성한다.

    Args:
        before_analysis: 변경 전 분석
        after_analysis: 변경 후 분석
        changed_cells: 변경된 셀 목록 (선택사항)

    Returns:
        ({
            "summary": str,
            "changes": [...],
            "impact": {...},
        }, error_or_None)
    """
    if not isinstance(before_analysis, dict) or not isinstance(after_analysis, dict):
        return None, "INVALID_ANALYSIS_DATA"

    try:
        comparison, err = compare_analyses(before_analysis, after_analysis)
        if err:
            return None, err

        changes = []

        # 테이블 구조 변경
        if comparison.get("table_structure_changed"):
            before_summary = comparison.get("before_summary", {})
            after_summary = comparison.get("after_summary", {})
            changes.append({
                "type": "table_structure",
                "description": "테이블 구조 변경",
                "details": {
                    "rows_before": before_summary.get("data_row_count"),
                    "rows_after": after_summary.get("data_row_count"),
                    "cols_before": before_summary.get("col_count"),
                    "cols_after": after_summary.get("col_count"),
                },
            })

        # 데이터 품질 변경
        if comparison.get("data_quality_changed"):
            quality_before = comparison.get("quality_before")
            quality_after = comparison.get("quality_after")
            delta = quality_after - quality_before if quality_after and quality_before else 0
            changes.append({
                "type": "data_quality",
                "description": "데이터 품질 변경",
                "details": {
                    "quality_before": quality_before,
                    "quality_after": quality_after,
                    "delta": round(delta, 2),
                },
            })

        # 수식 에러 변경
        if comparison.get("formula_errors_changed"):
            errors_before = comparison.get("errors_before", 0)
            errors_after = comparison.get("errors_after", 0)
            delta = errors_after - errors_before
            changes.append({
                "type": "formula_errors",
                "description": "수식 에러 변경",
                "details": {
                    "errors_before": errors_before,
                    "errors_after": errors_after,
                    "delta": delta,
                },
            })

        # 셀 값 변경
        if changed_cells:
            changes.append({
                "type": "cell_values",
                "description": f"{len(changed_cells)} 개 셀 값 변경",
                "details": {
                    "changed_count": len(changed_cells),
                    "samples": changed_cells[:5],
                },
            })

        # 영향 분석
        impact = _analyze_impact(comparison, changes)

        # 요약 문자열
        summary_lines = []
        if changes:
            summary_lines.append(f"총 {len(changes)} 가지 변경 발견:")
            for change in changes:
                summary_lines.append(f"  - {change['description']}")
        else:
            summary_lines.append("변경 사항 없음")

        return {
            "summary": "\n".join(summary_lines),
            "changes": changes,
            "impact": impact,
        }, None

    except Exception as e:  # noqa: BLE001
        logger.error("generate_change_summary 실패: %s", type(e).__name__)
        return None, "SUMMARY_GENERATION_FAILED"


def _analyze_impact(comparison: dict, changes: list) -> dict:
    """변경의 영향을 분석한다."""
    impact_level = "low"

    # 영향 레벨 결정
    if len(changes) > 3:
        impact_level = "high"
    elif len(changes) > 1:
        impact_level = "medium"

    # 특정 변경이 높은 영향을 나타내는지 확인
    for change in changes:
        if change["type"] == "table_structure":
            impact_level = "high"
        elif change["type"] == "formula_errors" and change.get("details", {}).get("delta", 0) > 0:
            impact_level = "high"

    return {
        "level": impact_level,  # low / medium / high
        "change_count": len(changes),
        "affected_areas": [c["type"] for c in changes],
    }
