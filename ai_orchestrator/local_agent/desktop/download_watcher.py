"""다운로드 폴더 감시 + 파일 분류."""
from __future__ import annotations

import threading
import time
from pathlib import Path

KAKAO_DOWNLOAD_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Pictures" / "카카오톡 받은 파일",
    Path.home() / "OneDrive" / "Pictures",
    Path.home() / "OneDrive" / "Downloads",
]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".aac"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".hwp", ".txt"}


def _classify_ext(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in DOC_EXTS:
        return "document"
    return "other"


def scan_existing(dirs=None) -> list[dict]:
    """기존 파일 스캔."""
    if dirs is None:
        dirs = KAKAO_DOWNLOAD_DIRS
    result = []
    for d in dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file():
                try:
                    st = f.stat()
                    result.append({
                        "path": str(f),
                        "name": f.name,
                        "type": _classify_ext(f),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    })
                except Exception:
                    pass
    return sorted(result, key=lambda x: x["mtime"], reverse=True)


class DownloadWatcher:
    """폴링 기반 다운로드 폴더 감시."""

    def __init__(self, dirs=None, callback=None, poll_interval: int = 15):
        self._dirs = dirs or KAKAO_DOWNLOAD_DIRS
        self._callback = callback
        self._interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def scan_existing(self) -> list[dict]:
        return scan_existing(self._dirs)

    def _run(self) -> None:
        seen: set[str] = {f["path"] for f in scan_existing(self._dirs)}
        while not self._stop.wait(timeout=self._interval):
            current = scan_existing(self._dirs)
            for f in current:
                if f["path"] not in seen:
                    seen.add(f["path"])
                    if self._callback:
                        try:
                            self._callback(f)
                        except Exception:
                            pass
