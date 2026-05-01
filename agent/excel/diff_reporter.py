"""변경 전후 diff 및 보고."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ValidationReport:
    """검증 보고서."""

    def __init__(self):
        self.errors: list[dict] = []
        self.warnings: list[dict] = []
        self.infos: list[dict] = []

    def add_error(self, issue_dict: dict) -> None:
        """오류 추가."""
        self.errors.append(issue_dict)

    def add_warning(self, issue_dict: dict) -> None:
        """경고 추가."""
        self.warnings.append(issue_dict)

    def add_info(self, issue_dict: dict) -> None:
        """정보 추가."""
        self.infos.append(issue_dict)

    def add_issue(self, issue_dict: dict) -> None:
        """심각도에 따라 자동 추가."""
        severity = issue_dict.get("severity", "info")
        if severity == "error":
            self.add_error(issue_dict)
        elif severity == "warning":
            self.add_warning(issue_dict)
        else:
            self.add_info(issue_dict)

    def is_valid(self) -> bool:
        """오류가 없는지 확인."""
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        """dict로 변환."""
        return {
            "success": self.is_valid(),
            "issues": [
                {"severity": "error", **e} for e in self.errors
            ] + [
                {"severity": "warning", **w} for w in self.warnings
            ] + [
                {"severity": "info", **i} for i in self.infos
            ],
            "summary": {
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "info": len(self.infos),
            },
        }


def build_change_diff(
    before_state: Optional[dict],
    after_state: Optional[dict],
) -> tuple[Optional[dict], Optional[str]]:
    """변경 전후 상태 diff를 생성한다.

    Args:
        before_state: {"cells": {...}, ...}
        after_state: {"cells": {...}, ...}

    Returns:
        ({"added": [...], "modified": [...], "deleted": [...]}, error_or_None)
    """
    try:
        diff = {
            "added_rows": [],
            "modified_cells": [],
            "added_columns": [],
            "new_formulas": [],
        }

        if before_state is None or after_state is None:
            return diff, None

        # 셀 변경 감지
        before_cells = before_state.get("cells", {})
        after_cells = after_state.get("cells", {})

        for cell_addr, after_value in after_cells.items():
            before_value = before_cells.get(cell_addr)

            if before_value is None:
                # 새로운 셀
                diff["added_rows"].append({
                    "cell": cell_addr,
                    "value": after_value,
                })
            elif before_value != after_value:
                # 수정된 셀
                if isinstance(after_value, str) and after_value.startswith("="):
                    diff["new_formulas"].append({
                        "cell": cell_addr,
                        "formula": after_value,
                        "old_value": before_value,
                    })
                else:
                    diff["modified_cells"].append({
                        "cell": cell_addr,
                        "old": before_value,
                        "new": after_value,
                    })

        # 열 추가 감지
        if "columns" in before_state and "columns" in after_state:
            before_cols = set(before_state["columns"])
            after_cols = set(after_state["columns"])
            new_cols = after_cols - before_cols
            if new_cols:
                diff["added_columns"] = list(new_cols)

        return diff, None

    except Exception as e:  # noqa: BLE001
        logger.error("build_change_diff failed: %s", type(e).__name__)
        return None, "DIFF_BUILD_FAILED"


def compare_formulas(
    before_formulas: dict[str, str],
    after_formulas: dict[str, str],
) -> tuple[Optional[list], Optional[str]]:
    """변경 전후 수식 비교.

    Args:
        before_formulas: {"A1": "=SUM(B1:B10)", ...}
        after_formulas: {"A1": "=SUM(B1:B11)", ...}

    Returns:
        ([issue_dict, ...], error_or_None)
    """
    try:
        issues = []

        for cell_addr, after_formula in after_formulas.items():
            before_formula = before_formulas.get(cell_addr)

            if before_formula is None:
                issues.append({
                    "type": "new_formula",
                    "cell": cell_addr,
                    "formula": after_formula,
                    "message": f"새로운 수식이 추가되었습니다.",
                })
            elif before_formula != after_formula:
                issues.append({
                    "type": "modified_formula",
                    "cell": cell_addr,
                    "before": before_formula,
                    "after": after_formula,
                    "message": f"수식이 변경되었습니다.",
                })

        return issues, None

    except Exception as e:  # noqa: BLE001
        logger.error("compare_formulas failed: %s", type(e).__name__)
        return None, "FORMULA_COMPARE_FAILED"
