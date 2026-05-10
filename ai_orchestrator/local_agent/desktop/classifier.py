"""파일/이미지 분류."""
from __future__ import annotations

import shutil
from pathlib import Path

from .download_watcher import _classify_ext, IMAGE_EXTS


def classify_file(path: Path) -> dict:
    """파일 분류.

    반환: {category, subcategory, suggested_folder, tags}
    """
    category = _classify_ext(path)
    name_lower = path.name.lower()
    ext = path.suffix.lower()

    subcategory = ""
    tags: list[str] = []

    if category == "image":
        # 스크린샷 패턴
        if any(k in name_lower for k in ("screenshot", "screen", "capture", "스크린")):
            subcategory = "screenshot"
            tags.append("스크린샷")
        else:
            subcategory = "photo"
            tags.append("사진")
        suggested_folder = "images/" + subcategory

    elif category == "document":
        if ext == ".pdf":
            subcategory = "pdf"
        elif ext in (".xlsx", ".xls"):
            subcategory = "spreadsheet"
        elif ext in (".docx", ".doc"):
            subcategory = "word"
        elif ext == ".hwp":
            subcategory = "hwp"
        else:
            subcategory = "text"
        tags.append("문서")
        suggested_folder = "documents/" + subcategory

    elif category == "video":
        subcategory = "video"
        tags.append("영상")
        suggested_folder = "videos"

    elif category == "audio":
        subcategory = "audio"
        tags.append("음성")
        suggested_folder = "audio"

    else:
        subcategory = "other"
        suggested_folder = "others"

    return {
        "category": category,
        "subcategory": subcategory,
        "suggested_folder": suggested_folder,
        "tags": tags,
    }


def organize_files(files: list[dict], base_dir: Path) -> dict:
    """분류 결과에 따라 파일을 base_dir 하위 폴더로 복사.

    files: classify_file 결과 + "path" 키 포함 dict 목록
    반환: {moved: int, skipped: int, errors: list}
    """
    moved = 0
    skipped = 0
    errors: list[str] = []

    for f in files:
        src = Path(f.get("path", ""))
        info = classify_file(src) if "suggested_folder" not in f else f
        dest_dir = base_dir / info["suggested_folder"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        if dest.exists():
            skipped += 1
            continue
        try:
            shutil.copy2(src, dest)
            moved += 1
        except Exception as e:
            errors.append(f"{src.name}: {e}")

    return {"moved": moved, "skipped": skipped, "errors": errors}
