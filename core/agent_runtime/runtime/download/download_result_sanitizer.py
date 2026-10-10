"""
다운로드 결과 sanitizer

다운로드 task 결과에서 민감 필드를 제거하고
서버 전송에 안전한 형태로 변환한다.

원칙:
- 원본 로컬 파일 경로는 서버에 전송하지 않는다.
- cookie/session/token/password/OTP/cert password 없음.
- 파일 바이너리/내용 자체는 전송하지 않는다.
- 메타데이터(이름, 크기, 확장자, 허용여부)만 전송한다.
"""
from __future__ import annotations

from typing import Any

# ── 민감 필드 목록 ─────────────────────────────────────────────────────────────

_SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "file_path", "local_path", "absolute_path", "full_path",
    "cookie", "cookies", "session", "token", "password", "otp",
    "certificate_password", "cert_password", "auth_token",
    "access_token", "refresh_token", "npki_data", "private_key",
    "localStorage", "sessionStorage", "Authorization", "auth_header",
    "file_content", "file_binary", "file_data", "raw_content",
})

# ── 안전 필드 (항상 False 강제) ────────────────────────────────────────────────

_FIXED_SAFE_FIELDS: dict[str, Any] = {
    "sensitive_data_detected": False,
    "cookie_exported": False,
    "session_exported": False,
    "password_collected": False,
    "otp_collected": False,
    "certificate_password_collected": False,
    "storage_state_exported": False,
    "file_content_exported": False,
    "local_path_exported": False,
}

# ── 파일 항목 내 허용 필드 ────────────────────────────────────────────────────

_ALLOWED_FILE_FIELDS: frozenset[str] = frozenset({
    "file_id", "safe_name", "extension", "size_bytes",
    "mime_type", "upload_allowed", "blocked_reason",
    "certificate_file_detected",
})


def sanitize_download_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    다운로드 task 결과에서 민감 필드를 제거한다.
    """
    safe: dict[str, Any] = {}
    removed: list[str] = []

    for k, v in result.items():
        if k in _SENSITIVE_FIELDS:
            removed.append(k)
        else:
            safe[k] = v

    # 파일 목록 내부 정제
    if "files" in safe and isinstance(safe["files"], list):
        safe["files"] = [_sanitize_file_entry(f) for f in safe["files"]]

    # extracted_data 내부 민감 키 제거
    if "extracted_data" in safe and isinstance(safe["extracted_data"], dict):
        safe["extracted_data"] = {
            k: v for k, v in safe["extracted_data"].items()
            if k not in _SENSITIVE_FIELDS
        }

    # 안전 필드 강제 설정
    safe.update(_FIXED_SAFE_FIELDS)

    if removed:
        safe["_sanitized_fields"] = removed

    return safe


def _sanitize_file_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """파일 항목에서 허용 필드만 남긴다."""
    return {k: v for k, v in entry.items() if k in _ALLOWED_FILE_FIELDS}


def validate_sanitized_download_result(result: dict[str, Any]) -> list[str]:
    """
    sanitize된 결과에 민감 필드가 없는지 검증한다.
    위반 목록 반환 (빈 = 안전).
    """
    violations: list[str] = []

    for field in _SENSITIVE_FIELDS:
        val = result.get(field)
        if val not in (None, False, "", [], {}):
            violations.append(f"민감 필드 잔존: {field!r}")

    for field, expected in _FIXED_SAFE_FIELDS.items():
        if result.get(field) is not expected:
            violations.append(f"고정 필드 불일치: {field!r} = {result.get(field)!r}")

    # 파일 목록 내부 검사
    for i, fentry in enumerate(result.get("files", [])):
        if isinstance(fentry, dict):
            for field in _SENSITIVE_FIELDS:
                if fentry.get(field) not in (None, False, "", [], {}):
                    violations.append(f"files[{i}] 민감 필드: {field!r}")

    return violations
