"""파일 이동 실행: shutil.move 수행 (승인 검증 후)."""

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agent.local_inventory.file_map.cleanup_preflight import PreflightReport


VALID_APPROVAL_TOKEN_PREFIX = "user-approved-cleanup"


@dataclass(frozen=True)
class ExecutionResult:
    """실행 결과."""

    run_id: str
    package_id: str
    timestamp: str
    success_count: int
    failed_count: int
    skipped_count: int
    conflict_count: int
    succeeded: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)


def validate_approval(
    approval_token: str,
    user_confirmed: bool,
    preflight_report: PreflightReport,
) -> None:
    """
    승인 토큰 및 사용자 확인 검증.

    Args:
        approval_token: "user-approved-cleanup-<uuid>" 형식
        user_confirmed: 사용자 최종 확인 (True 필수)
        preflight_report: PreflightReport (conflict/skipped/blocked 없어야 함)

    Raises:
        ValueError: 검증 실패
    """
    if not approval_token:
        raise ValueError("승인 토큰이 없습니다")

    if not approval_token.startswith(VALID_APPROVAL_TOKEN_PREFIX):
        raise ValueError(
            f"승인 토큰 형식 오류 ('{VALID_APPROVAL_TOKEN_PREFIX}-' 필수)"
        )

    if not user_confirmed:
        raise ValueError("사용자 최종 확인이 필요합니다")

    if not preflight_report or preflight_report.ok_count == 0:
        raise ValueError("승인 가능한 항목이 없습니다")

    if preflight_report.conflict_count > 0:
        raise ValueError("충돌하는 파일이 있어 실행할 수 없습니다")

    if preflight_report.blocked_count > 0:
        raise ValueError("제외된 파일이 있어 실행할 수 없습니다")


def execute_moves(
    preflight_report: PreflightReport,
    package_id: str,
    approval_token: str,
    user_confirmed_execution: bool,
    dry_run: bool = True,
) -> ExecutionResult:
    """
    사전검사 결과를 바탕으로 파일 이동 실행.

    Args:
        preflight_report: run_preflight()의 결과
        package_id: 실행 패키지 ID
        approval_token: 승인 토큰
        user_confirmed_execution: 사용자 최종 확인
        dry_run: True이면 실제 이동 안 함, False이면 실제 이동 수행

    Returns:
        ExecutionResult: 실행 결과

    Raises:
        ValueError: 승인 검증 실패
    """
    # 승인 검증
    validate_approval(approval_token, user_confirmed_execution, preflight_report)

    run_id = str(uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    succeeded = []
    failed = []
    skipped = []
    conflicts = []

    # ok 상태의 항목만 처리
    ok_items = [item for item in preflight_report.items if item.status == "ok"]

    for item in ok_items:
        source_path = Path(item.source_path)
        target_path = Path(item.target_path)

        try:
            # 소스 파일 존재 재확인
            if not source_path.exists():
                skipped.append(
                    {
                        "operation_id": item.operation_id,
                        "source_path": item.source_path,
                        "target_path": item.target_path,
                        "reason": "소스 파일이 존재하지 않습니다",
                    }
                )
                continue

            # 대상 경로에 파일 존재 여부 최종 확인
            if target_path.exists():
                conflicts.append(
                    {
                        "operation_id": item.operation_id,
                        "source_path": item.source_path,
                        "target_path": item.target_path,
                        "reason": "대상 경로에 같은 이름의 파일이 존재합니다",
                    }
                )
                continue

            # 대상 디렉토리 생성 확인
            target_dir = target_path.parent
            if not dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)

            # 실제 이동 (dry_run=False일 때만)
            if dry_run:
                # dry_run: 메타데이터만 기록
                succeeded.append(
                    {
                        "operation_id": item.operation_id,
                        "source_path": item.source_path,
                        "target_path": item.target_path,
                        "category": item.category,
                        "dry_run": True,
                        "file_size_bytes": source_path.stat().st_size,
                    }
                )
            else:
                # 실제 이동 수행
                shutil.move(str(source_path), str(target_path))
                succeeded.append(
                    {
                        "operation_id": item.operation_id,
                        "source_path": item.source_path,
                        "target_path": item.target_path,
                        "category": item.category,
                        "dry_run": False,
                        "file_size_bytes": target_path.stat().st_size,
                    }
                )

        except Exception as e:
            failed.append(
                {
                    "operation_id": item.operation_id,
                    "source_path": item.source_path,
                    "target_path": item.target_path,
                    "error": str(e),
                }
            )

    return ExecutionResult(
        run_id=run_id,
        package_id=package_id,
        timestamp=timestamp,
        success_count=len(succeeded),
        failed_count=len(failed),
        skipped_count=len(skipped),
        conflict_count=len(conflicts),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        conflicts=conflicts,
    )
