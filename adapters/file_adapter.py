"""
파일 어댑터 — 읽기/조회/preview만 허용, 실제 쓰기/삭제 금지
"""
import os
import difflib
from typing import Union

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".bin",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".pyc", ".pyo", ".pyd",
}


def _is_binary(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return False


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def _starts_with_dir(child: str, parent: str) -> bool:
    c = _norm(child)
    p = _norm(parent)
    return c == p or c.startswith(p + os.sep)


def _check_path(path: str, allowed_paths: list, blocked_paths: list) -> tuple[bool, str]:
    for bp in blocked_paths:
        if _starts_with_dir(path, bp):
            return False, f"path blocked: {path}"
    for ap in allowed_paths:
        if _starts_with_dir(path, ap):
            return True, ""
    return False, f"path not in allowed_paths: {path}"


def read_file(path: str, allowed_paths: list, blocked_paths: list) -> dict:
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}

    if not os.path.isfile(path):
        return {"status": "ERROR", "reason": f"file not found: {path}"}

    if _is_binary(path):
        return {"status": "BLOCKED", "reason": "binary files are not readable"}

    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        return {"status": "BLOCKED", "reason": f"file too large ({size} bytes > {MAX_FILE_SIZE})"}

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"status": "OK", "content": content, "size": size, "path": path}
    except OSError as e:
        return {"status": "ERROR", "reason": str(e)}


def list_dir(path: str, allowed_paths: list, blocked_paths: list) -> dict:
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}

    if not os.path.isdir(path):
        return {"status": "ERROR", "reason": f"not a directory: {path}"}

    try:
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            entries.append({
                "name": name,
                "type": "dir" if os.path.isdir(full) else "file",
                "size": os.path.getsize(full) if os.path.isfile(full) else None,
            })
        return {"status": "OK", "path": path, "entries": entries, "count": len(entries)}
    except OSError as e:
        return {"status": "ERROR", "reason": str(e)}


def file_exists(path: str, allowed_paths: list, blocked_paths: list) -> dict:
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}
    exists = os.path.exists(path)
    return {"status": "OK", "exists": exists, "path": path}


def preview_patch(path: str, new_content: str, allowed_paths: list, blocked_paths: list) -> dict:
    """diff 미리보기만 반환 — 실제 파일 저장 금지"""
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}

    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                original = f.read()
        except OSError as e:
            return {"status": "ERROR", "reason": str(e)}
    else:
        original = ""

    diff = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{os.path.basename(path)}",
        tofile=f"b/{os.path.basename(path)}",
    ))
    return {
        "status": "PREVIEW_ONLY",
        "path": path,
        "diff": "".join(diff),
        "note": "actual file was NOT modified",
    }
