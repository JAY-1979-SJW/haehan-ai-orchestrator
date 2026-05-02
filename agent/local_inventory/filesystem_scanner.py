"""파일 시스템 스캔 (메타데이터만, 내용 읽기 금지).

- 파일 메타데이터 수집
- 폴더 구조 스캔 (깊이/파일 수 제한)
- 확장자/경로 필터링
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.local_inventory.policy import (
    ALLOWED_EXTENSIONS,
    EXCLUDED_FOLDER_NAMES,
)
from agent.local_inventory.scan_scope import (
    is_excluded_folder,
    is_excluded_path,
)

logger = logging.getLogger(__name__)


@dataclass
class FileScanConfig:
    """파일 스캔 설정."""
    max_depth: int = 2
    max_files: int = 1000
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: frozenset(ALLOWED_EXTENSIONS)
    )
    excluded_folder_names: frozenset[str] = field(
        default_factory=lambda: frozenset(EXCLUDED_FOLDER_NAMES)
    )


@dataclass
class FileEntry:
    """파일 메타데이터."""
    path: str
    size_bytes: int
    modified_time: str  # ISO 8601
    extension: str


@dataclass
class DirectoryScanResult:
    """폴더 스캔 결과."""
    path: str
    exists: bool
    file_count: int = 0
    folder_count: int = 0
    total_size_bytes: int = 0
    file_types: dict[str, int] = field(default_factory=dict)  # ext → count
    truncated: bool = False  # max_files 초과
    error: Optional[str] = None
    last_modified: Optional[str] = None
    last_scanned: Optional[str] = None


def scan_file(path: str) -> Optional[FileEntry]:
    """파일 메타데이터 수집 (내용 읽기 금지).

    Args:
        path: 파일 경로

    Returns:
        FileEntry 또는 None (파일 없음)
    """
    try:
        p = Path(path)

        if not p.exists() or not p.is_file():
            return None

        stat = p.stat()
        mtime = datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"

        return FileEntry(
            path=str(p),
            size_bytes=stat.st_size,
            modified_time=mtime,
            extension=p.suffix.lower(),
        )

    except Exception as e:
        logger.warning(f"Failed to scan file {path}: {e}")
        return None


def scan_directory(
    path: str,
    config: FileScanConfig = FileScanConfig(),
) -> DirectoryScanResult:
    """폴더 메타데이터 수집 (깊이/파일 수 제한).

    Args:
        path: 폴더 경로
        config: 스캔 설정

    Returns:
        DirectoryScanResult
    """
    return _scan_directory_recursive(path, config, current_depth=0)


def _scan_directory_recursive(
    path: str,
    config: FileScanConfig,
    current_depth: int = 0,
) -> DirectoryScanResult:
    """재귀적 폴더 스캔."""
    try:
        p = Path(path)

        if not p.exists() or not p.is_dir():
            return DirectoryScanResult(
                path=path,
                exists=False,
                error="Path does not exist or is not a directory",
            )

        if is_excluded_path(str(p)):
            return DirectoryScanResult(
                path=path,
                exists=False,
                error="Path is excluded",
            )

        file_count = 0
        folder_count = 0
        total_size = 0
        file_types: dict[str, int] = {}
        last_modified: Optional[str] = None
        truncated = False

        try:
            for item in p.iterdir():
                # 깊이 초과
                if current_depth >= config.max_depth:
                    break

                # 제외 폴더 건너뛰기
                if item.is_dir() and is_excluded_folder(item.name):
                    continue

                try:
                    if item.is_file():
                        file_count += 1

                        # max_files 초과 시 truncate
                        if file_count > config.max_files:
                            truncated = True
                            break

                        stat = item.stat()
                        total_size += stat.st_size

                        # 확장자별 카운트 (allowed 확장자만)
                        ext = item.suffix.lower()
                        if ext in config.allowed_extensions:
                            file_types[ext] = file_types.get(ext, 0) + 1

                        # 최신 수정시간
                        mtime = datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
                        if last_modified is None or mtime > last_modified:
                            last_modified = mtime

                    elif item.is_dir():
                        folder_count += 1

                except (OSError, PermissionError):
                    continue

        except (OSError, PermissionError) as e:
            logger.warning(f"Error iterating directory {path}: {e}")

        return DirectoryScanResult(
            path=str(p),
            exists=True,
            file_count=file_count,
            folder_count=folder_count,
            total_size_bytes=total_size,
            file_types=file_types,
            truncated=truncated,
            last_modified=last_modified,
            last_scanned=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        logger.warning(f"Failed to scan directory {path}: {e}")
        return DirectoryScanResult(
            path=path,
            exists=False,
            error=str(e),
        )
