"""첨부 파일 안전 규칙 — 파일명 정리, 형식 차단, 크기 상한, 미리보기 가능 형식. 네트워크를 쓰지 않는다.

기준서: docs/specs/2026-10-01_naver_mailbox_tab.md 2·5절.
"""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 받을 때 첨부 1개 상한
MAX_UPLOAD_FILE_BYTES = 20 * 1024 * 1024  # 보낼 때 파일 1개 상한
MAX_UPLOAD_TOTAL_BYTES = 25 * 1024 * 1024  # 보낼 때 합계 상한(네이버 첨부 한도 40MB 안쪽)
MAX_UPLOAD_COUNT = 10
MAX_MESSAGE_BYTES = 60 * 1024 * 1024  # 메일 전체를 읽는 상한

# 실행·스크립트 형식은 보내지 않는다(네이버도 막는 형식 포함)
BLOCKED_EXTENSIONS = frozenset(
    {
        "exe", "bat", "cmd", "com", "scr", "pif", "msi", "msp", "dll", "sys", "lnk", "cpl",
        "js", "jse", "vbs", "vbe", "wsf", "wsh", "ps1", "psm1", "jar", "reg", "hta", "apk",
    }
)  # fmt: skip

# 읽기 창 안에서 보여 줘도 안전한 형식(SVG·HTML 은 스크립트 위험으로 제외)
PREVIEWABLE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain"})

_BAD_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def safe_filename(name: str | None, fallback: str = "첨부파일") -> str:
    """경로 문자·제어 문자를 없애고 150자로 줄인다(확장자는 유지)."""
    base = PurePosixPath((name or "").replace("\\", "/")).name
    cleaned = _BAD_CHARS.sub("_", base).strip(" .")
    if not cleaned:
        return fallback
    if len(cleaned) > 150:
        stem, dot, ext = cleaned.rpartition(".")
        cleaned = (stem[: 150 - len(ext) - 1] + dot + ext) if dot and len(ext) < 20 else cleaned[:150]
    return cleaned


def extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def is_blocked(name: str) -> bool:
    """마지막 확장자뿐 아니라 `report.exe.txt` 처럼 중간 확장자에 실행 형식이 끼어 있어도 막는다."""
    parts = safe_filename(name).lower().split(".")
    return any(p in BLOCKED_EXTENSIONS for p in parts[1:])


def guess_type(name: str, declared: str | None = None) -> tuple[str, str]:
    """(maintype, subtype). 선언된 형식이 이상하면 파일명으로 추정하고, 모르면 octet-stream."""
    candidate = (declared or "").split(";")[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", candidate):
        candidate = mimetypes.guess_type(name)[0] or "application/octet-stream"
    main, _, sub = candidate.partition("/")
    return main, sub


def is_previewable(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() in PREVIEWABLE_TYPES


@dataclass(frozen=True)
class Upload:
    filename: str
    content_type: str
    data: bytes


def validate_uploads(files: list[Upload]) -> list[Upload]:
    """보낼 첨부 검증 — 개수·크기·형식. 문제가 있으면 ValueError(사용자에게 보일 문구)."""
    if len(files) > MAX_UPLOAD_COUNT:
        raise ValueError(f"첨부는 최대 {MAX_UPLOAD_COUNT}개입니다")
    total, clean = 0, []
    for f in files:
        name = safe_filename(f.filename)
        if is_blocked(name):
            raise ValueError(f"보낼 수 없는 형식입니다: {name}")
        if not f.data:
            raise ValueError(f"빈 파일입니다: {name}")
        if len(f.data) > MAX_UPLOAD_FILE_BYTES:
            raise ValueError(f"파일 하나는 {MAX_UPLOAD_FILE_BYTES // 1024 // 1024}MB 이하여야 합니다: {name}")
        total += len(f.data)
        clean.append(Upload(name, f.content_type, f.data))
    if total > MAX_UPLOAD_TOTAL_BYTES:
        raise ValueError(f"첨부 합계는 {MAX_UPLOAD_TOTAL_BYTES // 1024 // 1024}MB 이하여야 합니다")
    return clean
