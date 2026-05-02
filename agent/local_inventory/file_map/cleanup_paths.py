"""경로 안전성 검증: 소스 존재, 대상 충돌, 경로 길이 확인."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.local_inventory.file_map.cleanup_policy import is_system_path


@dataclass(frozen=True)
class PathCheckResult:
    """경로 검증 결과."""

    path: str
    source_exists: bool
    target_exists: bool
    is_system_path: bool
    path_too_long: bool
    error: Optional[str]


MAX_PATH_LENGTH = 260  # Windows MAX_PATH


def check_source(path: str) -> PathCheckResult:
    """소스 경로 검증 (존재, 시스템 경로, 경로 길이)."""
    if not path:
        return PathCheckResult(
            path=path,
            source_exists=False,
            target_exists=False,
            is_system_path=False,
            path_too_long=False,
            error="경로가 비어있습니다",
        )

    path_obj = Path(path)
    is_sys = is_system_path(str(path_obj.resolve()))
    is_too_long = len(str(path_obj.resolve())) > MAX_PATH_LENGTH
    exists = path_obj.exists()

    error = None
    if is_sys:
        error = "시스템 경로는 이동할 수 없습니다"
    elif is_too_long:
        error = f"경로가 너무 깁니다 ({len(str(path_obj.resolve()))} > {MAX_PATH_LENGTH})"
    elif not exists:
        error = "소스 파일이 존재하지 않습니다"

    return PathCheckResult(
        path=str(path_obj.resolve()),
        source_exists=exists,
        target_exists=False,
        is_system_path=is_sys,
        path_too_long=is_too_long,
        error=error,
    )


def check_conflict(source: str, target_dir: str) -> bool:
    """대상 경로에 같은 이름의 파일이 있는지 확인."""
    if not source or not target_dir:
        return False

    source_obj = Path(source)
    target_path = Path(target_dir) / source_obj.name

    return target_path.exists()


def build_target_path(source: str, target_base_dir: str) -> str:
    """소스 파일명을 사용하여 대상 전체 경로 생성."""
    if not source or not target_base_dir:
        return ""

    source_obj = Path(source)
    target_base = Path(target_base_dir)

    # 절대 경로로 변환
    source_abs = source_obj.resolve()
    target_base_abs = target_base.resolve()

    # 대상 디렉토리가 시스템 경로면 거부
    if is_system_path(str(target_base_abs)):
        return ""

    # 대상 경로 생성 (소스의 파일명 사용)
    target_full = target_base_abs / source_abs.name

    # 결과 경로가 시스템 경로면 거부
    if is_system_path(str(target_full)):
        return ""

    return str(target_full)
