"""
다운로드 업로드 manifest 생성기

다운로드 task 결과에서 서버 업로드용 safe manifest를 생성한다.

manifest에 포함되는 정보:
- task_id
- 파일 safe_name, extension, size_bytes, mime_type
- upload_allowed, blocked_reason
- sensitive_data_detected: false (항상)
- certificate_file_detected: false or true (탐지 여부)

manifest에 포함하지 않는 정보:
- 로컬 파일 경로
- 파일 바이너리/내용
- cookie/session/token/password/OTP/cert password
"""

from __future__ import annotations

import uuid
from typing import Any

from core.agent_runtime.runtime.download.download_policy import (
    check_file,
)
from core.agent_runtime.runtime.download.download_result_sanitizer import (
    sanitize_download_result,
    validate_sanitized_download_result,
)

# ── MIME 타입 매핑 (확장자 기반) ──────────────────────────────────────────────

_EXT_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".hwpx": "application/x-hwpx",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".zip": "application/zip",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def build_manifest(
    task_id: str,
    downloaded_files: list[dict[str, Any]],
    task_downloaded_filenames: list[str] | None = None,
) -> dict[str, Any]:
    """
    서버 업로드용 safe manifest를 생성한다.

    downloaded_files: [{"filename": str, "size_bytes": int?, "file_path": str?}, ...]
    task_downloaded_filenames: 이번 task가 다운로드한 파일명 목록 (None이면 검사 생략)

    반환:
      task_id, files[], sensitive_data_detected, certificate_file_detected
    """
    file_entries: list[dict[str, Any]] = []
    any_cert_detected = False

    for f in downloaded_files:
        filename = f.get("filename", "")
        size_bytes = f.get("size_bytes")
        file_path = f.get("file_path")

        policy = check_file(
            filename=filename,
            size_bytes=size_bytes,
            file_path=file_path,
            task_downloaded_files=task_downloaded_filenames,
        )

        ext = policy["extension"]
        mime = _EXT_TO_MIME.get(ext, "application/octet-stream")

        entry: dict[str, Any] = {
            "file_id": str(uuid.uuid4()),
            "safe_name": policy["safe_name"],
            "extension": ext,
            "size_bytes": size_bytes,
            "mime_type": mime,
            "upload_allowed": policy["upload_allowed"],
            "blocked_reason": policy["blocked_reason"],
            "certificate_file_detected": policy.get("certificate_file_detected", False),
        }

        if policy.get("certificate_file_detected"):
            any_cert_detected = True

        file_entries.append(entry)

    manifest: dict[str, Any] = {
        "task_id": task_id,
        "files": file_entries,
        "sensitive_data_detected": False,
        "certificate_file_detected": any_cert_detected,
        "total_files": len(file_entries),
        "allowed_count": sum(1 for e in file_entries if e["upload_allowed"]),
        "blocked_count": sum(1 for e in file_entries if not e["upload_allowed"]),
    }

    # sanitize 적용
    return sanitize_download_result(manifest)


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """
    manifest의 민감정보 포함 여부를 검증한다.
    위반 목록 반환 (빈 = 안전).
    """
    violations = validate_sanitized_download_result(manifest)

    # 파일 항목별 원본 경로 노출 검사
    for i, entry in enumerate(manifest.get("files", [])):
        if isinstance(entry, dict):
            if entry.get("file_path") or entry.get("local_path") or entry.get("absolute_path"):
                violations.append(f"files[{i}] 원본 경로 노출")

    return violations


def is_safe_manifest(manifest: dict[str, Any]) -> bool:
    """manifest가 서버 전송에 안전한지 확인한다."""
    return len(validate_manifest(manifest)) == 0
