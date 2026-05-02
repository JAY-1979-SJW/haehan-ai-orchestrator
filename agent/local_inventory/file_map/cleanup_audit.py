"""감사로그: JSONL 형식으로 저장/조회."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_AUDIT_FILE = Path.home() / "AppData/Local/HaehanAI/inventory/cleanup_audit.jsonl"


@dataclass(frozen=True)
class AuditRecord:
    """감사로그 레코드."""

    run_id: str
    timestamp: str
    package_id: str
    operation_id: str
    operation_type: str  # "move"
    status: str  # success|failed|skipped|conflict
    source_path: str  # 마스킹 정책 적용
    target_path: str  # 마스킹 정책 적용
    category: str
    risk: str  # "low" | "medium" | "high"
    error: Optional[str] = None


def _mask_path(path: str) -> str:
    """기본 마스킹: 경로를 해시값으로 치환."""
    if not path:
        return ""
    # 간단한 마스킹: 파일명만 노출, 경로는 숨김
    path_obj = Path(path)
    return f"[MASKED_PATH]/{path_obj.name}"


def save_records(
    records: list[AuditRecord], audit_file: Path = DEFAULT_AUDIT_FILE
) -> None:
    """
    감사로그를 JSONL 파일에 추가.

    Args:
        records: AuditRecord 리스트
        audit_file: 저장 위치
    """
    if not records:
        return

    # 디렉토리 생성
    audit_file.parent.mkdir(parents=True, exist_ok=True)

    # JSONL 형식으로 추가
    with open(audit_file, "a", encoding="utf-8") as f:
        for record in records:
            record_dict = asdict(record)
            # 마스킹 적용
            record_dict["source_path"] = _mask_path(record.source_path)
            record_dict["target_path"] = _mask_path(record.target_path)
            f.write(json.dumps(record_dict, ensure_ascii=False) + "\n")


def load_records(
    run_id: Optional[str] = None, audit_file: Path = DEFAULT_AUDIT_FILE
) -> list[dict]:
    """
    감사로그를 조회.

    Args:
        run_id: 특정 run_id로 필터링 (None이면 전체)
        audit_file: 읽을 파일 위치

    Returns:
        AuditRecord dict 리스트
    """
    if not audit_file.exists():
        return []

    records = []
    with open(audit_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if run_id is None or record.get("run_id") == run_id:
                    records.append(record)
            except json.JSONDecodeError:
                # 잘못된 라인 무시
                continue

    return records


def create_audit_records_from_execution(
    run_id: str,
    package_id: str,
    execution_result: dict,
) -> list[AuditRecord]:
    """
    ExecutionResult를 AuditRecord 리스트로 변환.

    Args:
        run_id: 실행 ID
        package_id: 패키지 ID
        execution_result: ExecutionResult dict (succeeded/failed/skipped/conflicts)

    Returns:
        AuditRecord 리스트
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    records = []

    # 성공한 항목
    for item in execution_result.get("succeeded", []):
        records.append(
            AuditRecord(
                run_id=run_id,
                timestamp=timestamp,
                package_id=package_id,
                operation_id=item.get("operation_id", ""),
                operation_type="move",
                status="success",
                source_path=item.get("source_path", ""),
                target_path=item.get("target_path", ""),
                category=item.get("category", ""),
                risk="low",
                error=None,
            )
        )

    # 실패한 항목
    for item in execution_result.get("failed", []):
        records.append(
            AuditRecord(
                run_id=run_id,
                timestamp=timestamp,
                package_id=package_id,
                operation_id=item.get("operation_id", ""),
                operation_type="move",
                status="failed",
                source_path=item.get("source_path", ""),
                target_path=item.get("target_path", ""),
                category="",
                risk="high",
                error=item.get("error"),
            )
        )

    # 스킵된 항목
    for item in execution_result.get("skipped", []):
        records.append(
            AuditRecord(
                run_id=run_id,
                timestamp=timestamp,
                package_id=package_id,
                operation_id=item.get("operation_id", ""),
                operation_type="move",
                status="skipped",
                source_path=item.get("source_path", ""),
                target_path=item.get("target_path", ""),
                category="",
                risk="medium",
                error=item.get("reason"),
            )
        )

    # 충돌 항목
    for item in execution_result.get("conflicts", []):
        records.append(
            AuditRecord(
                run_id=run_id,
                timestamp=timestamp,
                package_id=package_id,
                operation_id=item.get("operation_id", ""),
                operation_type="move",
                status="conflict",
                source_path=item.get("source_path", ""),
                target_path=item.get("target_path", ""),
                category="",
                risk="high",
                error=item.get("reason"),
            )
        )

    return records
