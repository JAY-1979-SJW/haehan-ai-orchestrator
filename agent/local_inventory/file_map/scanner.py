"""파일 메타데이터 스캐너.

파일 경로, 크기, 수정일 등 메타데이터만 수집.
파일 내용은 읽지 않음.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional

from .models import FileMetadata, ScanOptions, DEFAULT_EXCLUDED_DIRS


class FileMapScanner:
    """파일 메타데이터 수집기."""

    def __init__(self) -> None:
        self.files: list[FileMetadata] = []
        self.scan_errors: list[dict] = []
        self.scan_start: Optional[datetime] = None
        self.scan_end: Optional[datetime] = None

    def scan(self, options: ScanOptions) -> tuple[list[FileMetadata], dict]:
        """지정된 폴더를 스캔하고 파일 메타데이터 수집."""
        self.files = []
        self.scan_errors = []
        self.scan_start = datetime.now()

        target = Path(options.target_directory)
        if not target.exists() or not target.is_dir():
            return [], {
                "ok": False,
                "error": f"Directory not found: {target}",
                "scanned_files": 0,
            }

        # 제외 디렉토리 구성
        excluded = DEFAULT_EXCLUDED_DIRS.copy()
        if options.excluded_dirs:
            excluded.update(options.excluded_dirs)

        # 재귀 스캔
        self._scan_directory(
            target,
            current_depth=0,
            max_depth=options.scan_depth,
            max_files=options.max_files,
            allowed_extensions=options.allowed_extensions,
            excluded_dirs=excluded,
            exclude_hidden=options.exclude_hidden,
        )

        self.scan_end = datetime.now()

        return self.files, {
            "ok": True,
            "scanned_files": len(self.files),
            "scan_duration_seconds": (self.scan_end - self.scan_start).total_seconds(),
            "errors": len(self.scan_errors),
        }

    def _scan_directory(
        self,
        directory: Path,
        current_depth: int,
        max_depth: int,
        max_files: int,
        allowed_extensions: Optional[list[str]],
        excluded_dirs: set[str],
        exclude_hidden: bool,
    ) -> None:
        """재귀적으로 디렉토리 스캔."""
        if current_depth >= max_depth or len(self.files) >= max_files:
            return

        try:
            for item in directory.iterdir():
                if len(self.files) >= max_files:
                    break

                try:
                    # 제외 디렉토리 확인
                    if item.is_dir():
                        if item.name in excluded_dirs:
                            continue
                        if exclude_hidden and item.name.startswith("."):
                            continue

                        # 재귀 스캔
                        self._scan_directory(
                            item,
                            current_depth + 1,
                            max_depth,
                            max_files,
                            allowed_extensions,
                            excluded_dirs,
                            exclude_hidden,
                        )
                    else:
                        # 파일 메타데이터 수집
                        if exclude_hidden and item.name.startswith("."):
                            continue

                        # 확장자 필터링
                        if allowed_extensions:
                            if item.suffix.lower() not in allowed_extensions:
                                continue

                        # 메타데이터 추출
                        try:
                            stat = item.stat()
                            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                            created = datetime.fromtimestamp(stat.st_ctime).isoformat()

                            file_meta = FileMetadata(
                                path=str(item),
                                name=item.name,
                                extension=item.suffix.lower(),
                                size_bytes=stat.st_size,
                                modified_time=modified,
                                created_time=created,
                                is_hidden=item.name.startswith("."),
                            )
                            self.files.append(file_meta)

                        except OSError as e:
                            self.scan_errors.append({
                                "file": str(item),
                                "error": str(e),
                            })

                except Exception as e:
                    self.scan_errors.append({
                        "file": str(item),
                        "error": str(e),
                    })

        except PermissionError:
            self.scan_errors.append({
                "directory": str(directory),
                "error": "Permission denied",
            })
        except Exception as e:
            self.scan_errors.append({
                "directory": str(directory),
                "error": str(e),
            })
