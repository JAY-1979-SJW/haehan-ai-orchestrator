"""
파일 어댑터 — 읽기/조회/preview만 허용, 실제 쓰기/삭제 금지
"""

import difflib
import os
from pathlib import Path

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".pyc",
    ".pyo",
    ".pyd",
}


def _is_binary(path: str) -> bool:
    ext = Path(path).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return True
    try:
        with Path(path).open("rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return False


def _norm(p: str) -> str:
    # os.path.abspath 유지(STD-02 pathlib 전환 예외): Path.resolve()는 심볼릭 링크를
    # 따라가는데, 이 함수는 allowed/blocked 경로 포함 여부를 판정하는 보안 경계
    # 로직(_check_path)에 쓰인다 — 심볼릭 링크로 우회 가능한 다른 정규화로 바꾸면
    # 판정 의미가 바뀔 위험이 있어 기존 동작(symlink 미해석)을 그대로 유지한다.
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

    if not Path(path).is_file():
        return {"status": "ERROR", "reason": f"file not found: {path}"}

    if _is_binary(path):
        return {"status": "BLOCKED", "reason": "binary files are not readable"}

    size = Path(path).stat().st_size
    if size > MAX_FILE_SIZE:
        return {"status": "BLOCKED", "reason": f"file too large ({size} bytes > {MAX_FILE_SIZE})"}

    try:
        with Path(path).open(encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"status": "OK", "content": content, "size": size, "path": path}
    except OSError as e:
        return {"status": "ERROR", "reason": str(e)}


def list_dir(path: str, allowed_paths: list, blocked_paths: list) -> dict:
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}

    if not Path(path).is_dir():
        return {"status": "ERROR", "reason": f"not a directory: {path}"}

    try:
        entries = []
        for full in sorted(Path(path).iterdir(), key=lambda p: p.name):
            entries.append(
                {
                    "name": full.name,
                    "type": "dir" if full.is_dir() else "file",
                    "size": full.stat().st_size if full.is_file() else None,
                }
            )
        return {"status": "OK", "path": path, "entries": entries, "count": len(entries)}
    except OSError as e:
        return {"status": "ERROR", "reason": str(e)}


def file_exists(path: str, allowed_paths: list, blocked_paths: list) -> dict:
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}
    exists = Path(path).exists()
    return {"status": "OK", "exists": exists, "path": path}


def preview_patch(path: str, new_content: str, allowed_paths: list, blocked_paths: list) -> dict:
    """diff 미리보기만 반환 — 실제 파일 저장 금지"""
    ok, msg = _check_path(path, allowed_paths, blocked_paths)
    if not ok:
        return {"status": "BLOCKED", "reason": msg}

    if Path(path).is_file():
        try:
            with Path(path).open(encoding="utf-8", errors="replace") as f:
                original = f.read()
        except OSError as e:
            return {"status": "ERROR", "reason": str(e)}
    else:
        original = ""

    diff = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{Path(path).name}",
            tofile=f"b/{Path(path).name}",
        )
    )
    return {
        "status": "PREVIEW_ONLY",
        "path": path,
        "diff": "".join(diff),
        "note": "actual file was NOT modified",
    }
