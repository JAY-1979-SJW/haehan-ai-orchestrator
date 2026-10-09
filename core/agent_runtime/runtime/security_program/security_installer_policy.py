"""Security Installer Policy — 설치 파일 안전 정책 검증."""
from __future__ import annotations

import hashlib
from typing import Any

# 허용 확장자
_ALLOWED_EXTENSIONS = frozenset((".exe", ".msi", ".dmg", ".pkg", ".zip"))

# 차단 확장자 (중복 정의 — candidate_finder와 독립적으로 동작)
_BLOCKED_EXTENSIONS = frozenset((
    ".bat", ".cmd", ".ps1", ".js", ".vbs", ".sh",
    ".pfx", ".p12", ".key", ".pem", ".crt", ".cer",
))

# 무인 설치 플래그 — 자동 사용 금지
_SILENT_FLAGS = frozenset((
    "/silent", "/quiet", "/qn", "/verysilent",
    "-silent", "-quiet", "-qn",
    "--silent", "--quiet",
    "/s", "-s",
))

# 최대 허용 파일 크기 (500MB)
_MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024

# 결과 상태
POLICY_ALLOWED = "POLICY_ALLOWED"
POLICY_BLOCKED = "POLICY_BLOCKED"
POLICY_NEEDS_USER_DIRECT = "POLICY_NEEDS_USER_DIRECT"
POLICY_NEEDS_PERMISSION = "POLICY_NEEDS_PERMISSION"


def _collect_violations(
    ext: str, file_size_bytes: int | None, install_args: list[str] | None, is_official_source: bool
) -> list[str]:
    violations: list[str] = []

    # 확장자 검증
    if ext in _BLOCKED_EXTENSIONS:
        violations.append(f"차단 확장자: {ext}")

    # 파일 크기 검증
    if file_size_bytes is not None and file_size_bytes > _MAX_FILE_SIZE_BYTES:
        violations.append(f"파일 크기 초과: {file_size_bytes} bytes")

    # 무인 설치 플래그 검증
    silent_detected: list[str] = []
    if install_args:
        for arg in install_args:
            if arg.lower() in _SILENT_FLAGS:
                silent_detected.append(arg)
    if silent_detected:
        violations.append(f"무인 설치 플래그 자동 사용 금지: {silent_detected}")

    # 공식 출처 미확인
    if not is_official_source:
        violations.append("공식 출처 미확인 — USER_DIRECT 필요")
    return violations


def evaluate_installer(
    filename: str,
    source_host: str,
    is_official_source: bool = False,
    file_size_bytes: int | None = None,
    install_args: list[str] | None = None,
    has_user_permission: bool = False,
) -> dict[str, Any]:
    """
    설치 파일의 안전 정책을 평가한다.

    Returns:
        {
            "policy": POLICY_*,
            "executable": bool,
            "grade": "AUTO_ALLOWED"|"USER_DELEGATED"|"USER_DIRECT"|"BLOCKED",
            "violations": list[str],
            "install_args_safe": bool,
            "requires_uac": bool,
            "hash_recorded": str|None,
        }
    """
    ext = _get_extension(filename.lower())
    violations = _collect_violations(ext, file_size_bytes, install_args, is_official_source)

    if violations:
        # 무인 설치나 차단 확장자는 BLOCKED
        has_blocked = any(
            "차단 확장자" in v or "무인 설치" in v
            for v in violations
        )
        if has_blocked:
            return _result(POLICY_BLOCKED, "BLOCKED", violations)
        # 공식 출처 미확인은 USER_DIRECT
        return _result(POLICY_NEEDS_USER_DIRECT, "USER_DIRECT_REQUIRED", violations)

    # exe/msi/dmg/pkg → USER_DELEGATED (관리자 권한 필요)
    requires_uac = ext in (".exe", ".msi")

    if not has_user_permission:
        return {
            "policy": POLICY_NEEDS_PERMISSION,
            "executable": False,
            "grade": "USER_DELEGATED_PERMISSION_REQUIRED",
            "violations": [],
            "install_args_safe": True,
            "requires_uac": requires_uac,
            "hash_recorded": None,
        }

    return {
        "policy": POLICY_ALLOWED,
        "executable": True,
        "grade": "USER_DELEGATED_PERMISSION_REQUIRED",
        "violations": [],
        "install_args_safe": True,
        "requires_uac": requires_uac,
        "hash_recorded": None,
    }


def check_silent_flags(install_args: list[str]) -> list[str]:
    """무인 설치 플래그 목록 반환."""
    return [arg for arg in install_args if arg.lower() in _SILENT_FLAGS]


def record_installer_hash(file_bytes: bytes) -> str:
    """설치 파일 SHA256 해시를 기록한다."""
    return hashlib.sha256(file_bytes).hexdigest()


def _get_extension(filename: str) -> str:
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1]
    return ""


def _result(policy: str, grade: str, violations: list[str]) -> dict[str, Any]:
    return {
        "policy": policy,
        "executable": False,
        "grade": grade,
        "violations": violations,
        "install_args_safe": False,
        "requires_uac": False,
        "hash_recorded": None,
    }
