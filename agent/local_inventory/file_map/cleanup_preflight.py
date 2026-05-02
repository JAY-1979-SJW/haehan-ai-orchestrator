"""사전검사: policy와 paths를 조합하여 preflight 실행."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agent.local_inventory.file_map.cleanup_policy import (
    is_allowed_group,
    is_always_excluded_group,
    is_huge_file,
    is_sensitive_file,
    get_exclusion_reason,
)
from agent.local_inventory.file_map.cleanup_paths import check_source, check_conflict, build_target_path


@dataclass(frozen=True)
class PreflightItem:
    """사전검사 항목."""

    operation_id: str
    source_path: str
    target_path: str
    category: str
    status: str  # "ok" | "conflict" | "source_missing" | "system_path" | "blocked"
    reason: str


@dataclass(frozen=True)
class PreflightReport:
    """사전검사 리포트."""

    preflight_id: str
    total: int
    ok_count: int
    conflict_count: int
    skipped_count: int
    blocked_count: int
    items: list[PreflightItem] = field(default_factory=list)


def run_preflight(
    plans: list[dict],
    base_target_dir: str,
    include_sensitive: bool = False,
) -> PreflightReport:
    """
    정리 계획 목록을 사전검사하여 PreflightReport 생성.

    Args:
        plans: CleanupPlan dict 목록 (operation_id, path, category, file_size_bytes)
        base_target_dir: 대상 기본 디렉토리 (e.g., "C:\\Users\\user\\클린업")
        include_sensitive: 민감문서 포함 여부

    Returns:
        PreflightReport: 사전검사 결과
    """
    if not plans:
        return PreflightReport(
            preflight_id=str(uuid4()),
            total=0,
            ok_count=0,
            conflict_count=0,
            skipped_count=0,
            blocked_count=0,
            items=[],
        )

    items = []
    ok_count = 0
    conflict_count = 0
    skipped_count = 0
    blocked_count = 0

    for plan in plans:
        operation_id = plan.get("operation_id", str(uuid4()))
        source_path = plan.get("path", "")
        category = plan.get("category", "unknown")
        file_size = plan.get("file_size_bytes")
        file_name = plan.get("file_name", "")

        # 1. 그룹 확인: always_excluded에 속하는가?
        if is_always_excluded_group(category):
            reason = get_exclusion_reason(category, include_sensitive)
            if reason:  # None이 아니면 제외
                items.append(
                    PreflightItem(
                        operation_id=operation_id,
                        source_path=source_path,
                        target_path="",
                        category=category,
                        status="blocked",
                        reason=reason,
                    )
                )
                blocked_count += 1
                continue

        # 2. 그룹 확인: allowed 그룹인가?
        if not is_allowed_group(category):
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path="",
                    category=category,
                    status="blocked",
                    reason=f"'{category}' 그룹은 허용되지 않습니다",
                )
            )
            blocked_count += 1
            continue

        # 3. 민감문서 확인
        if is_sensitive_file(file_name):
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path="",
                    category=category,
                    status="blocked",
                    reason="민감문서 - 수동 확인 필요",
                )
            )
            blocked_count += 1
            continue

        # 4. 대용량 파일 확인
        if is_huge_file(file_size):
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path="",
                    category=category,
                    status="blocked",
                    reason="대용량 파일(1GB+) - 별도 검토 필요",
                )
            )
            blocked_count += 1
            continue

        # 5. 소스 경로 검증
        source_check = check_source(source_path)
        if source_check.error:
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path="",
                    category=category,
                    status="source_missing" if not source_check.source_exists else "system_path",
                    reason=source_check.error,
                )
            )
            skipped_count += 1
            continue

        # 6. 대상 경로 생성
        target_path = build_target_path(source_path, base_target_dir)
        if not target_path:
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path="",
                    category=category,
                    status="system_path",
                    reason="대상 경로가 시스템 경로를 초과합니다",
                )
            )
            skipped_count += 1
            continue

        # 7. 대상 충돌 확인
        if check_conflict(source_path, base_target_dir):
            items.append(
                PreflightItem(
                    operation_id=operation_id,
                    source_path=source_path,
                    target_path=target_path,
                    category=category,
                    status="conflict",
                    reason="대상 경로에 같은 이름의 파일이 존재합니다",
                )
            )
            conflict_count += 1
            continue

        # 8. 모든 검사 통과
        items.append(
            PreflightItem(
                operation_id=operation_id,
                source_path=source_path,
                target_path=target_path,
                category=category,
                status="ok",
                reason="",
            )
        )
        ok_count += 1

    return PreflightReport(
        preflight_id=str(uuid4()),
        total=len(plans),
        ok_count=ok_count,
        conflict_count=conflict_count,
        skipped_count=skipped_count,
        blocked_count=blocked_count,
        items=items,
    )
