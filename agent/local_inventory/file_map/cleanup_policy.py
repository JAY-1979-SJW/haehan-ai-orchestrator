"""파일 정리 정책: 허용/제외 그룹, 민감 파일, 시스템 경로 판별."""

from pathlib import Path

# 허용 그룹
ALLOWED_GROUPS = {"documents", "spreadsheets", "cad", "images", "archive"}

# 기본 제외 그룹
ALWAYS_EXCLUDED_GROUPS = {
    "sensitive",
    "duplicates",
    "high_risk",
    "hold",
    "unknown",
    "recent_files",
}

# 파일 크기 임계값
HUGE_FILE_THRESHOLD = 1024 ** 3  # 1GB

# 시스템 경로 제외 (case-insensitive)
SYSTEM_EXCLUDED_PREFIXES = [
    ":\\Windows",
    ":\\Program Files",
    ":\\Program Files (x86)",
    "\\AppData\\",
    "\\.git",
    "\\node_modules",
    "\\venv",
    "\\.venv",
    "\\__pycache__",
    "\\.pytest_cache",
]

# 민감 파일 패턴
SENSITIVE_FILE_PATTERNS = {
    "신분증",
    "주민등록증",
    "운전면허",
    "여권",
    "통장",
    "계좌",
    "금융",
    "은행",
    "급여",
    "노임",
    "형사",
    "고소",
    "소송",
    "변호인",
    "기밀",
}


def is_allowed_group(group_id: str) -> bool:
    """그룹이 실행 허용 목록에 있는지 확인."""
    return group_id in ALLOWED_GROUPS


def is_always_excluded_group(group_id: str) -> bool:
    """그룹이 항상 제외 목록에 있는지 확인."""
    return group_id in ALWAYS_EXCLUDED_GROUPS


def is_sensitive_file(name: str) -> bool:
    """민감 파일인지 확인 (패턴 매칭)."""
    if not name:
        return False
    name_upper = name.upper()
    return any(pattern.upper() in name_upper for pattern in SENSITIVE_FILE_PATTERNS)


def is_huge_file(size_bytes: int | None) -> bool:
    """파일이 대용량(1GB+)인지 확인."""
    if size_bytes is None:
        return False
    return size_bytes >= HUGE_FILE_THRESHOLD


def is_system_path(path: str | Path) -> bool:
    """시스템 경로인지 확인 (절대 경로 생성 금지)."""
    if not path:
        return False
    path_str = str(path).upper()
    return any(prefix.upper() in path_str for prefix in SYSTEM_EXCLUDED_PREFIXES)


def get_exclusion_reason(
    group_id: str, include_sensitive: bool = False
) -> str | None:
    """제외 사유 반환 (None이면 허용)."""
    if is_always_excluded_group(group_id):
        if group_id == "sensitive":
            if not include_sensitive:
                return "민감문서 기본 제외"
            return None
        elif group_id == "duplicates":
            return "중복 검토 대상 (수동 확인 필요)"
        else:
            return f"'{group_id}' 그룹 기본 제외"
    return None
