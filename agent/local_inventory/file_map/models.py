"""파일 지도 데이터 모델.

파일 메타데이터, 분류, 중복 정보를 담는 데이터 클래스.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class FileMetadata:
    """파일 메타데이터."""
    path: str
    name: str
    extension: str
    size_bytes: int
    modified_time: str  # ISO format
    created_time: Optional[str] = None
    is_hidden: bool = False


@dataclass(frozen=True)
class FileClassification:
    """파일 분류."""
    file_path: str
    category: str  # document, spreadsheet, image, archive, etc.
    confidence: float  # 0.0 ~ 1.0
    notes: Optional[str] = None


@dataclass(frozen=True)
class DuplicateSuspicion:
    """중복 의심."""
    primary_path: str
    similar_paths: list[str]
    suspicion_reason: str  # "same_name", "same_size", "copy_pattern"
    severity: str  # "high", "medium", "low"


@dataclass(frozen=True)
class FileMapReport:
    """파일 지도 보고서."""
    scan_timestamp: str
    scanned_directory: str
    scan_duration_seconds: float

    total_files: int
    total_size_bytes: int

    files_by_category: dict[str, int]

    large_files: list[dict]  # 대용량 파일
    old_files: list[dict]  # 오래된 파일
    suspicious_duplicates: list[dict]  # 중복 의심
    suspicious_temp: list[dict]  # 임시/다운로드 의심

    recommendations: list[str]


@dataclass(frozen=True)
class ScanOptions:
    """파일 스캔 옵션."""
    target_directory: str
    scan_depth: int = 3  # 최대 깊이
    max_files: int = 10000  # 최대 파일 수
    allowed_extensions: Optional[list[str]] = None  # None = 모두
    excluded_dirs: Optional[list[str]] = None
    exclude_hidden: bool = True
    exclude_system_dirs: bool = True


# 기본 제외 디렉토리
DEFAULT_EXCLUDED_DIRS = {
    "node_modules",
    ".git",
    ".github",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    ".egg-info",
    "dist",
    "build",
    ".vscode",
    ".idea",
    "target",
    "bin",
    "obj",
}

# 파일 분류별 확장자
FILE_CATEGORIES = {
    "document": {".hwp", ".hwpx", ".doc", ".docx", ".pdf", ".txt", ".md"},
    "spreadsheet": {".xls", ".xlsx", ".xlsm", ".csv", ".ods"},
    "cad": {".dwg", ".dxf", ".step", ".stp", ".iges"},
    "image": {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"},
    "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".m4a"},
    "archive": {".zip", ".7z", ".rar", ".tar", ".gz"},
    "code": {".py", ".js", ".ts", ".java", ".cpp", ".cs", ".go", ".rs"},
}

# 임시/다운로드 의심 패턴
TEMP_SUSPICION_PATTERNS = {
    "download",
    "다운로드",
    "temp",
    "임시",
    "새 폴더",
    "복사본",
    "사본",
    "copy",
    "final",
    "최종",
    "진짜최종",
    "v1",
    "v2",
    "v3",
    "backup",
    "old",
    "archive",
}

# 대용량 파일 기준 (100MB)
LARGE_FILE_THRESHOLD_BYTES = 100 * 1024 * 1024

# 오래된 파일 기준 (1년)
OLD_FILE_DAYS = 365
