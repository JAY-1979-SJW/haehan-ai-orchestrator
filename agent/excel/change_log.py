"""변경 로그 기록."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional
from datetime import datetime


@dataclass(frozen=True)
class OperationLog:
    """단일 operation 실행 로그."""
    operation_type: str
    sheet: str
    status: str  # "success", "failed"
    message: str
    details: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict:
        """dict로 변환."""
        return asdict(self)


@dataclass(frozen=True)
class ChangeLog:
    """변경 전체 로그."""
    success: bool
    total_operations: int
    executed_operations: int
    failed_at_index: Optional[int]  # None이면 모두 성공
    logs: list[OperationLog]
    summary: dict[str, Any]

    def to_dict(self) -> dict:
        """dict로 변환."""
        return {
            "success": self.success,
            "total_operations": self.total_operations,
            "executed_operations": self.executed_operations,
            "failed_at_index": self.failed_at_index,
            "logs": [log.to_dict() for log in self.logs],
            "summary": self.summary,
        }


class ChangeLogBuilder:
    """변경 로그 작성자."""

    def __init__(self, total_operations: int):
        self.total_operations = total_operations
        self.logs: list[OperationLog] = []
        self.failed_at_index: Optional[int] = None

    def add_success(
        self,
        operation_type: str,
        sheet: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        """성공 로그 추가."""
        log = OperationLog(
            operation_type=operation_type,
            sheet=sheet,
            status="success",
            message=message,
            details=details or {},
            timestamp=datetime.now().isoformat(),
        )
        self.logs.append(log)

    def add_failure(
        self,
        operation_type: str,
        sheet: str,
        message: str,
        details: Optional[dict] = None,
    ) -> None:
        """실패 로그 추가."""
        if self.failed_at_index is None:
            self.failed_at_index = len(self.logs)

        log = OperationLog(
            operation_type=operation_type,
            sheet=sheet,
            status="failed",
            message=message,
            details=details or {},
            timestamp=datetime.now().isoformat(),
        )
        self.logs.append(log)

    def build(self) -> ChangeLog:
        """최종 로그 빌드."""
        success_count = len([log for log in self.logs if log.status == "success"])
        failure_count = len([log for log in self.logs if log.status == "failed"])

        return ChangeLog(
            success=failure_count == 0,
            total_operations=self.total_operations,
            executed_operations=len(self.logs),
            failed_at_index=self.failed_at_index,
            logs=self.logs,
            summary={
                "success_count": success_count,
                "failure_count": failure_count,
                "execution_time": "auto-calculated",
            },
        )
