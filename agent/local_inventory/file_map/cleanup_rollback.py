"""롤백 매니페스트: 생성/저장 (자동 롤백 실행 금지)."""

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ROLLBACK_DIR = Path.home() / "AppData/Local/HaehanAI/inventory"


@dataclass(frozen=True)
class RollbackEntry:
    """롤백 항목."""

    operation_id: str
    original_path: str
    moved_to_path: str
    rollback_possible: bool
    timestamp: str


@dataclass(frozen=True)
class RollbackManifest:
    """롤백 매니페스트."""

    run_id: str
    package_id: str
    generated_at: str
    total_moved: int
    entries: list[RollbackEntry] = field(default_factory=list)
    notes: str = "롤백은 수동으로만 수행 가능합니다. 자동 롤백은 지원하지 않습니다."


def create_manifest(
    run_id: str,
    package_id: str,
    execution_result: dict,
) -> RollbackManifest:
    """
    ExecutionResult를 RollbackManifest로 변환.

    Args:
        run_id: 실행 ID
        package_id: 패키지 ID
        execution_result: ExecutionResult dict (succeeded 필드)

    Returns:
        RollbackManifest
    """
    timestamp = datetime.now(UTC).isoformat()
    entries = []

    succeeded = execution_result.get("succeeded", [])
    for item in succeeded:
        entries.append(
            RollbackEntry(
                operation_id=item.get("operation_id", ""),
                original_path=item.get("source_path", ""),
                moved_to_path=item.get("target_path", ""),
                rollback_possible=True,
                timestamp=timestamp,
            )
        )

    return RollbackManifest(
        run_id=run_id,
        package_id=package_id,
        generated_at=timestamp,
        total_moved=len(entries),
        entries=entries,
        notes="롤백은 수동으로만 수행 가능합니다. 자동 롤백은 지원하지 않습니다.",
    )


def save_manifest(manifest: RollbackManifest, rollback_dir: Path = DEFAULT_ROLLBACK_DIR) -> Path:
    """
    롤백 매니페스트를 JSON 파일로 저장.

    Args:
        manifest: RollbackManifest
        rollback_dir: 저장 디렉토리

    Returns:
        저장된 파일 경로
    """
    rollback_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = rollback_dir / f"rollback_{manifest.run_id}.json"

    manifest_dict = asdict(manifest)
    tmp_file = manifest_file.with_suffix(manifest_file.suffix + ".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(manifest_dict, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, manifest_file)

    return manifest_file


def load_manifest(run_id: str, rollback_dir: Path = DEFAULT_ROLLBACK_DIR) -> dict | None:
    """
    롤백 매니페스트를 JSON 파일에서 로드.

    Args:
        run_id: 실행 ID
        rollback_dir: 읽을 디렉토리

    Returns:
        RollbackManifest dict (로드 실패 시 None)
    """
    manifest_file = rollback_dir / f"rollback_{run_id}.json"

    if not manifest_file.exists():
        return None

    try:
        with open(manifest_file, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None
