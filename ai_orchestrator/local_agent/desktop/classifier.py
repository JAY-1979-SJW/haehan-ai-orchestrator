"""파일 분류 + 자동 정리.

카카오톡/카카오워크 자동저장 파일을 출처/날짜/카테고리별로 정리.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .download_watcher import (
    _classify_ext, _infer_source, IMAGE_EXTS,
    KAKAOTALK_INBOX, KAKAOWORK_INBOX,
)

# 분류된 파일이 최종 정리되는 곳
_PROCESSED_BASE = KAKAOTALK_INBOX.parent / "_processed"


def classify_file(path: Path, room_hint: str | None = None) -> dict:
    """파일 분류.

    room_hint: 채팅방 이름 (있으면 폴더 구조에 포함)
    반환: {category, subcategory, source, room, suggested_folder, tags}
    """
    category = _classify_ext(path)
    source = _infer_source(path)
    name_lower = path.name.lower()
    ext = path.suffix.lower()

    subcategory = ""
    tags: list[str] = [source]

    if category == "image":
        if any(k in name_lower for k in ("screenshot", "screen", "capture", "스크린")):
            subcategory = "screenshot"; tags.append("스크린샷")
        else:
            subcategory = "photo"; tags.append("사진")
    elif category == "document":
        sub_map = {".pdf": "pdf", ".xlsx": "spreadsheet", ".xls": "spreadsheet",
                   ".docx": "word", ".doc": "word", ".hwp": "hwp",
                   ".pptx": "presentation", ".ppt": "presentation"}
        subcategory = sub_map.get(ext, "text")
        tags.append("문서")
    elif category == "video":
        subcategory = "video"; tags.append("영상")
    elif category == "audio":
        subcategory = "audio"; tags.append("음성")
    elif category == "archive":
        subcategory = "archive"; tags.append("압축")
    else:
        subcategory = "other"

    # 폴더 구조: source / category / subcategory (room 있으면 source/room/category)
    if room_hint:
        suggested_folder = f"{source}/{_safe_folder(room_hint)}/{category}"
    else:
        suggested_folder = f"{source}/{category}/{subcategory}"

    return {
        "category": category,
        "subcategory": subcategory,
        "source": source,
        "room": room_hint or "",
        "suggested_folder": suggested_folder,
        "tags": tags,
    }


def _safe_folder(name: str) -> str:
    """파일/폴더명으로 사용 가능하게 정리."""
    bad = '<>:"/\\|?*'
    return "".join(c if c not in bad else "_" for c in name).strip()[:60]


def organize_file(path: Path, room_hint: str | None = None,
                  base_dir: Path | None = None,
                  copy: bool = False) -> dict:
    """파일 1개 자동 정리.

    base_dir: 기본 _processed 폴더
    copy: True면 복사, False면 이동
    """
    if base_dir is None:
        base_dir = _PROCESSED_BASE

    info = classify_file(path, room_hint=room_hint)
    # 날짜별 추가 분리: _processed/YYYY-MM/source/category/...
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        mtime = datetime.now()
    month = mtime.strftime("%Y-%m")
    dest_dir = base_dir / month / info["suggested_folder"]
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / path.name
    if dest.exists():
        return {**info, "dest": str(dest), "status": "skipped_exists"}

    try:
        if copy:
            shutil.copy2(path, dest)
        else:
            shutil.move(str(path), str(dest))
        return {**info, "dest": str(dest), "status": "moved" if not copy else "copied"}
    except Exception as e:
        return {**info, "dest": str(dest), "status": f"error: {e}"}


def organize_files(files: list[dict], base_dir: Path | None = None,
                   copy: bool = True) -> dict:
    """배치 정리. files: scan_existing 결과."""
    moved = 0; skipped = 0; errors: list[str] = []
    for f in files:
        src = Path(f.get("path", ""))
        if not src.exists():
            continue
        result = organize_file(src, base_dir=base_dir, copy=copy)
        status = result.get("status", "")
        if status.startswith("moved") or status.startswith("copied"):
            moved += 1
        elif status.startswith("skip"):
            skipped += 1
        else:
            errors.append(f"{src.name}: {status}")
    return {"moved": moved, "skipped": skipped, "errors": errors}
