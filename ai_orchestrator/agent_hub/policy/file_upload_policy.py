"""
서버 사이드 파일 업로드 정책

서버는 로컬 에이전트가 전송한 manifest를 검증하고
실제 파일 업로드를 허용/차단한다.

서버 금지:
- 외부 사이트에서 직접 파일 다운로드
- 인증서/NPKI 파일 수신
- cookie/session/token/password/OTP/cert password 수신
- 파일 바이너리 직접 수신 (manifest 메타데이터만 수신)
- 실행파일 수신
"""
from __future__ import annotations

from typing import Any

# ── 서버 수신 허용 MIME ────────────────────────────────────────────────────────

_SERVER_ALLOWED_MIMES: frozenset[str] = frozenset({
    "application/pdf",
    "application/x-hwpx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
})

# ── 서버 수신 차단 MIME ───────────────────────────────────────────────────────

_SERVER_BLOCKED_MIMES: frozenset[str] = frozenset({
    "application/x-pkcs12",       # pfx, p12
    "application/x-x509-ca-cert", # cer, crt, der
    "application/x-pem-file",     # pem
    "application/octet-stream",   # 알 수 없는 바이너리 → 차단
    "application/x-msdownload",   # exe, dll
    "application/x-sh",           # sh
    "text/javascript",            # js
    "application/x-bat",          # bat
})

# ── 서버 수신 manifest 민감 필드 ──────────────────────────────────────────────

_MANIFEST_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "file_path", "local_path", "absolute_path", "full_path",
    "cookie", "cookies", "session", "token", "password", "otp",
    "certificate_password", "cert_password", "auth_token",
    "access_token", "refresh_token", "npki_data", "private_key",
    "file_content", "file_binary", "file_data",
})

# ── 서버 파일 크기 제한 (50MB) ────────────────────────────────────────────────

SERVER_MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024


def _forbidden_field_violations(obj: dict[str, Any], label: str) -> list[str]:
    """obj 내 민감 필드 값이 채워져 있으면 위반 메시지 목록을 반환한다."""
    return [
        f"{label} 민감 필드: {field!r}"
        for field in _MANIFEST_FORBIDDEN_FIELDS
        if obj.get(field) not in (None, False, "", [], {})
    ]


def validate_upload_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """
    서버가 수신한 manifest를 검증한다.

    반환:
      allowed: bool
      violations: list[str]
      safe_files: list[dict]  (업로드 허용 파일만)
    """
    violations: list[str] = []

    # manifest 최상위 민감 필드 검사
    violations.extend(_forbidden_field_violations(manifest, "manifest"))

    # 인증서 감지 여부
    if manifest.get("certificate_file_detected"):
        violations.append("manifest에 인증서 파일 포함 감지")

    # 파일 항목별 검사
    safe_files: list[dict[str, Any]] = []
    for i, entry in enumerate(manifest.get("files", [])):
        if not isinstance(entry, dict):
            violations.append(f"files[{i}] 형식 오류")
            continue

        # 파일 항목 내 민감 필드
        violations.extend(_forbidden_field_violations(entry, f"files[{i}]"))

        # 업로드 허용 여부
        if not entry.get("upload_allowed"):
            continue  # 차단된 파일은 safe_files에 포함 안 함

        # MIME 타입 검사
        mime = entry.get("mime_type", "")
        if mime in _SERVER_BLOCKED_MIMES:
            violations.append(f"files[{i}] 차단 MIME: {mime!r}")
            continue

        # 크기 검사
        size = entry.get("size_bytes")
        if size is not None and size > SERVER_MAX_FILE_SIZE_BYTES:
            violations.append(f"files[{i}] 크기 초과: {size}")
            continue

        safe_files.append(entry)

    allowed = len(violations) == 0

    return {
        "allowed": allowed,
        "violations": violations,
        "safe_files": safe_files,
        "sensitive_data_received": False,
        "certificate_received": False,
    }


def get_server_upload_policy_summary() -> dict[str, Any]:
    """서버 업로드 정책 요약을 반환한다."""
    return {
        "server_downloads_from_external": False,
        "server_receives_file_binary": False,
        "server_receives_credentials": False,
        "allowed_mimes": sorted(_SERVER_ALLOWED_MIMES),
        "blocked_mimes": sorted(_SERVER_BLOCKED_MIMES),
        "max_file_size_bytes": SERVER_MAX_FILE_SIZE_BYTES,
        "certificate_upload_allowed": False,
        "npki_upload_allowed": False,
        "executable_upload_allowed": False,
    }
