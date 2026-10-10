"""L6 서비스 — 하나팩스 첨부 파일: 올리기(앱 전용 폴더에 저장)·검사(형식·크기·내용 머리)·오래된 파일 정리.

기준서: docs/specs/2026-10-02_hanafax_auto_send.md §19
- 사용자가 경로를 직접 치지 않아도 되도록 화면에서 파일을 골라 올리면 앱 폴더(`ai_orchestrator/storage/fax_attachments/`, 커밋 제외)에 저장하고 그 경로를 돌려준다.
  앱 폴더 안이라 승인서의 허용 폴더 검사를 그대로 통과한다.
- 형식은 pdf/docx/doc 만, 크기는 사이트 제한(10MB) 이하, **확장자와 파일 내용 머리(매직 바이트)가 맞아야** 한다(이름만 바꾼 파일 거부).
- 승인서가 참조하는 파일은 지우지 않고, 참조되지 않는 30일 지난 업로드만 정리한다.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import storage_dir

MAX_BYTES = 10 * 1024 * 1024  # 하나팩스 접수 화면 안내: 파일 크기 10MB 이하
_MAGIC = {".pdf": (b"%PDF",), ".docx": (b"PK\x03\x04",), ".doc": (b"\xd0\xcf\x11\xe0",)}
_UPLOAD_DIR = storage_dir() / "fax_attachments"
_NAME_CLEAN = re.compile(r"[^\w.\-() 가-힣]")


def _human(size: int) -> str:
    return f"{size / 1024 / 1024:.1f}MB" if size >= 1024 * 1024 else f"{max(size // 1024, 1)}KB"


def inspect_file(path: Path | str) -> dict[str, Any]:
    """존재하는 파일의 형식·크기·내용 머리를 검사한다. 문제 있으면 ValueError(사람이 읽는 사유)."""
    p = Path(path)
    if not p.is_file():
        raise ValueError("파일을 찾을 수 없습니다")
    ext = p.suffix.lower()
    if ext not in _MAGIC:
        raise ValueError(f"허용되지 않는 형식입니다({ext or '확장자 없음'}) — pdf, docx, doc 만 보낼 수 있습니다")
    size = p.stat().st_size
    if size == 0:
        raise ValueError("빈 파일입니다")
    if size > MAX_BYTES:
        raise ValueError(f"파일이 너무 큽니다({_human(size)}) — 하나팩스는 10MB 이하만 받습니다")
    with p.open("rb") as fh:
        head = fh.read(8)
    if not any(head.startswith(m) for m in _MAGIC[ext]):
        raise ValueError(f"파일 내용이 {ext} 형식이 아닙니다(이름만 바꾼 파일은 보낼 수 없습니다)")
    return {"name": p.name, "size": size, "size_text": _human(size)}


def save_upload(filename: str, data: bytes) -> dict[str, Any]:
    """올린 파일을 검사해 앱 전용 폴더에 저장한다. 반환: {path, name, size, size_text}."""
    base = _NAME_CLEAN.sub("_", Path(str(filename or "")).name).strip(" .")[:80]
    ext = Path(base).suffix.lower()
    if not base or ext not in _MAGIC:
        raise ValueError(f"허용되지 않는 형식입니다({ext or '확장자 없음'}) — pdf, docx, doc 만 보낼 수 있습니다")
    if len(data) > MAX_BYTES:
        raise ValueError(f"파일이 너무 큽니다({_human(len(data))}) — 하나팩스는 10MB 이하만 받습니다")
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = _UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{base}"
    target.write_bytes(data)
    try:
        info = inspect_file(target)
    except ValueError:
        target.unlink(missing_ok=True)  # 검사에 통과하지 못한 파일은 남기지 않는다
        raise
    return {"path": str(target.resolve()), **info}


def purge_old(referenced: set[str], days: int = 30) -> int:
    """승인서가 참조하지 않는 `days` 일 지난 업로드를 지운다. 지운 개수를 돌려준다."""
    if not _UPLOAD_DIR.is_dir():
        return 0
    keep = {str(Path(p).resolve()) for p in referenced if p}
    cutoff = time.time() - days * 86400
    removed = 0
    for f in _UPLOAD_DIR.iterdir():
        if f.is_file() and str(f.resolve()) not in keep and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    return removed
