"""
다운로드 파일 업로드 정책

로컬 Playwright 에이전트가 다운로드한 파일을 서버에 업로드하기 전
허용/차단 여부를 판정한다.

원칙:
- 해당 task가 다운로드한 파일만 처리한다.
- 사용자 PC 다운로드 폴더 전체 스캔 금지.
- 원본 파일 삭제 금지.
- 인증서/NPKI 파일 업로드 금지.
- 민감 파일명 업로드 금지.
- 실행파일 업로드 금지.
"""

from __future__ import annotations

import os
from typing import Any

# ── 허용 확장자 ────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".hwpx",
        ".xlsx",
        ".xls",
        ".docx",
        ".zip",
        ".txt",
        ".csv",
        ".png",
        ".jpg",
        ".jpeg",
    }
)

# ── 차단 확장자 (인증서/키/실행파일) ──────────────────────────────────────────

BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # 인증서/키
        ".pfx",
        ".p12",
        ".der",
        ".key",
        ".pem",
        ".crt",
        ".cer",
        ".jks",
        ".p7b",
        ".p7c",
        ".p8",
        ".p15",
        ".pub",
        # 실행파일
        ".exe",
        ".msi",
        ".bat",
        ".cmd",
        ".ps1",
        ".js",
        ".vbs",
        ".sh",
        ".py",
        ".jar",
        ".dll",
        ".so",
        ".dmg",
        ".pkg",
        # 기타 위험
        ".lnk",
        ".scr",
        ".com",
        ".hta",
        ".reg",
    }
)

# ── NPKI/인증서 경로 패턴 ──────────────────────────────────────────────────────

NPKI_PATH_PATTERNS: tuple[str, ...] = (
    "npki",
    "NPKI",
    "usercert",
    "signCert",
    "signPri",
    "인증서",
    "certificate",
    "npkicard",
)

# ── 민감 파일명 패턴 ───────────────────────────────────────────────────────────

SENSITIVE_NAME_PATTERNS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "session",
    "credential",
    "private_key",
    "apikey",
    "api_key",
    "access_key",
    "auth",
    "비밀번호",
    "인증서",
    "otp",
)

# ── 파일 크기 제한 (50MB) ─────────────────────────────────────────────────────

MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024


def check_file(
    filename: str,
    size_bytes: int | None = None,
    file_path: str | None = None,
    task_downloaded_files: list[str] | None = None,
) -> dict[str, Any]:
    """
    단일 파일의 업로드 허용 여부를 판정한다.

    filename: 파일명 (확장자 포함)
    size_bytes: 파일 크기 (None이면 크기 검사 생략)
    file_path: 로컬 경로 (NPKI 경로 검사용, None이면 생략)
    task_downloaded_files: 이번 task가 다운로드한 파일명 목록 (None이면 검사 생략)

    반환:
      upload_allowed: bool
      blocked_reason: str | None
      extension: str
      safe_name: str  (원본 경로 제거, 파일명만)
    """
    ext = _get_extension(filename)
    safe_name = _safe_filename(filename)

    # task 외부 파일 차단
    if task_downloaded_files is not None:
        if filename not in task_downloaded_files and safe_name not in task_downloaded_files:
            return _block(safe_name, ext, "task 외부 파일: 이번 task가 다운로드하지 않은 파일")

    # NPKI/인증서 경로 차단 (확장자 검사보다 먼저)
    if file_path and _is_npki_path(file_path):
        return _block(safe_name, ext, "NPKI/인증서 경로 내 파일")

    # 차단 확장자
    if ext in BLOCKED_EXTENSIONS:
        return _block(safe_name, ext, f"차단 확장자: {ext!r}")

    # 민감 파일명 차단
    reason = _check_sensitive_name(safe_name)
    if reason:
        return _block(safe_name, ext, reason)

    # 허용 확장자 검사
    if ext not in ALLOWED_EXTENSIONS:
        return _block(safe_name, ext, f"허용되지 않은 확장자: {ext!r}")

    # 파일 크기 검사
    if size_bytes is not None and size_bytes > MAX_FILE_SIZE_BYTES:
        return _block(safe_name, ext, f"파일 크기 초과: {size_bytes} bytes > {MAX_FILE_SIZE_BYTES}")

    return {
        "upload_allowed": True,
        "blocked_reason": None,
        "extension": ext,
        "safe_name": safe_name,
        "certificate_file_detected": False,
        "sensitive_data_detected": False,
    }


def check_files(
    files: list[dict[str, Any]],
    task_downloaded_files: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    파일 목록 전체를 검사한다.

    files: [{"filename": str, "size_bytes": int, "file_path": str}, ...]
    반환: check_file 결과 목록
    """
    results = []
    for f in files:
        result = check_file(
            filename=f.get("filename", ""),
            size_bytes=f.get("size_bytes"),
            file_path=f.get("file_path"),
            task_downloaded_files=task_downloaded_files,
        )
        results.append(result)
    return results


def _get_extension(filename: str) -> str:
    # STD-02 예외: 반환값이 ALLOWED_EXTENSIONS/BLOCKED_EXTENSIONS 판정에 쓰이는
    # 보안 허용/차단 로직이며, _safe_filename()과 함께 동일 파일명을 다루므로
    # 두 함수의 trailing-slash 처리 방식을 일치시켜 둔다(os.path 유지). 테스트 커버리지 없이
    # Path.suffix 로 바꾸면 엣지케이스 회귀를 검증할 수 없어 보수적으로 SKIP.
    _, ext = os.path.splitext(filename)
    return ext.lower()


def _safe_filename(filename: str) -> str:
    """경로를 제거하고 파일명만 반환한다."""
    # STD-02 예외: safe_name은 check_file()에서 task_downloaded_files 식별자 비교에도
    # 쓰인다. os.path.basename("a/b/")=="" 이지만 Path("a/b/").name=="b"로 동작이 달라
    # (trailing slash 엣지케이스), 식별자 비교 의미가 바뀔 위험이 있다. 테스트 커버리지 없이
    # 이 보안 관련 판정을 바꾸지 않고 보수적으로 SKIP.
    return os.path.basename(filename)


def _is_npki_path(path: str) -> bool:
    lower = path.lower().replace("\\", "/")
    return any(p.lower() in lower for p in NPKI_PATH_PATTERNS)


def _check_sensitive_name(filename: str) -> str | None:
    lower = filename.lower()
    for pattern in SENSITIVE_NAME_PATTERNS:
        if pattern in lower:
            return f"민감 패턴 포함 파일명: {pattern!r}"
    return None


def _block(safe_name: str, ext: str, reason: str) -> dict[str, Any]:
    return {
        "upload_allowed": False,
        "blocked_reason": reason,
        "extension": ext,
        "safe_name": safe_name,
        "certificate_file_detected": ext in BLOCKED_EXTENSIONS
        and ext in {".pfx", ".p12", ".der", ".key", ".pem", ".crt", ".cer"},
        "sensitive_data_detected": False,
    }
