"""변경 작업(operation) 스키마 정의."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

# Operation 타입 상수
OP_UPDATE_CELL = "update_cell_by_header"
OP_INSERT_ROW = "insert_row_by_header"
OP_INSERT_COLUMN = "insert_column_by_header"
OP_WRITE_FORMULA = "write_formula_by_header"
OP_FILL_DOWN_FORMULA = "fill_down_formula"
OP_COPY_STYLE = "copy_style"
OP_APPLY_NUMBER_FORMAT = "apply_number_format"
OP_APPLY_HIGHLIGHT = "apply_highlight"
OP_CREATE_SUMMARY_SHEET = "create_summary_sheet"
OP_EXPORT_PDF_COPY = "export_pdf_copy"

KNOWN_OPERATIONS = frozenset({
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
})

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

KNOWN_RISKS = frozenset({RISK_LOW, RISK_MEDIUM, RISK_HIGH})


@dataclass(frozen=True)
class Operation:
    """단일 변경 작업."""
    type: str
    sheet: str
    risk: str
    params: dict[str, Any]

    def __post_init__(self) -> None:
        if self.type not in KNOWN_OPERATIONS:
            raise ValueError(f"Unknown operation type: {self.type}")
        if self.risk not in KNOWN_RISKS:
            raise ValueError(f"Unknown risk level: {self.risk}")
        if not isinstance(self.sheet, str) or not self.sheet:
            raise ValueError("sheet must be a non-empty string")
        if not isinstance(self.params, dict):
            raise ValueError("params must be a dict")

    def to_dict(self) -> dict:
        """Operation을 dict로 변환."""
        return {
            "type": self.type,
            "sheet": self.sheet,
            "risk": self.risk,
            "params": self.params,
        }


@dataclass(frozen=True)
class ChangePlan:
    """변경 계획."""
    success: bool
    dry_run: bool
    operations: list[Operation]
    requires_approval: bool
    will_modify_original: bool
    save_mode: str  # "copy_only", "save_as", "overwrite"
    error: Optional[str] = None
    warnings: list[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.operations, list):
            raise ValueError("operations must be a list")
        for op in self.operations:
            if not isinstance(op, Operation):
                raise ValueError("All items in operations must be Operation instances")
        if self.save_mode not in ("copy_only", "save_as", "overwrite"):
            raise ValueError("save_mode must be one of: copy_only, save_as, overwrite")
        # warnings은 None이 아니면 list여야 함
        if self.warnings is not None and not isinstance(self.warnings, list):
            raise ValueError("warnings must be None or a list")

    def to_dict(self) -> dict:
        """ChangePlan을 dict로 변환."""
        return {
            "success": self.success,
            "dry_run": self.dry_run,
            "operations": [op.to_dict() for op in self.operations],
            "requires_approval": self.requires_approval,
            "will_modify_original": self.will_modify_original,
            "save_mode": self.save_mode,
            "error": self.error,
            "warnings": self.warnings or [],
        }
