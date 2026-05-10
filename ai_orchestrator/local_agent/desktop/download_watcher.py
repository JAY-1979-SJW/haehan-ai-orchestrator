"""다운로드 폴더 감시 + 파일 분류.

카카오톡/카카오워크 자동저장 폴더 + 일반 다운로드 폴더 통합 감시.
새 파일 발견 시 출처 추정(카카오톡/카카오워크/일반) + 활성 채팅방 매핑.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트 기준 (ai_orchestrator/local_agent/desktop/download_watcher.py → 4 levels up)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_KAKAO_INBOX = _REPO_ROOT / "data" / "kakao_inbox"

# 사용자가 카카오 환경설정에 등록할 표준 경로
KAKAOTALK_INBOX = _KAKAO_INBOX / "kakaotalk"
KAKAOWORK_INBOX = _KAKAO_INBOX / "kakaowork"

# 일반 다운로드 (카카오톡 환경설정 미적용 시 fallback)
GENERAL_DOWNLOAD_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Pictures" / "카카오톡 받은 파일",
    Path.home() / "OneDrive" / "Pictures",
    Path.home() / "OneDrive" / "Downloads",
]

DEFAULT_WATCH_DIRS = [
    KAKAOTALK_INBOX,
    KAKAOWORK_INBOX,
    *GENERAL_DOWNLOAD_DIRS,
]

# 카카오톡 PC 캐시 (썸네일 자동 저장됨 — 메타데이터 추출용)
_KAKAOTALK_CACHE = Path.home() / "AppData" / "Local" / "Kakao" / "KakaoTalk" / "users"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".aac"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".hwp", ".txt", ".csv"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz"}


def _classify_ext(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:    return "image"
    if ext in VIDEO_EXTS:    return "video"
    if ext in AUDIO_EXTS:    return "audio"
    if ext in DOC_EXTS:      return "document"
    if ext in ARCHIVE_EXTS:  return "archive"
    return "other"


def _infer_source(path: Path) -> str:
    """파일 경로 → 출처 추정 (kakaotalk / kakaowork / general)."""
    p = str(path).lower()
    if "kakao_inbox" in p and "kakaotalk" in p:   return "kakaotalk"
    if "kakao_inbox" in p and "kakaowork" in p:   return "kakaowork"
    if "kakaotalk" in p or "카카오톡" in str(path): return "kakaotalk"
    if "kakaowork" in p or "카카오워크" in str(path): return "kakaowork"
    return "general"


def scan_existing(dirs=None, age_hours: int | None = None) -> list[dict]:
    """기존 파일 스캔.

    age_hours: 지정 시 최근 N시간 내 수정된 파일만.
    """
    if dirs is None:
        dirs = DEFAULT_WATCH_DIRS
    cutoff = None
    if age_hours is not None:
        cutoff = time.time() - age_hours * 3600

    result = []
    for d in dirs:
        if not d.exists():
            continue
        try:
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        st = f.stat()
                        if cutoff and st.st_mtime < cutoff:
                            continue
                        result.append({
                            "path": str(f),
                            "name": f.name,
                            "type": _classify_ext(f),
                            "source": _infer_source(f),
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                            "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(),
                        })
                    except Exception:
                        pass
        except Exception:
            pass
    return sorted(result, key=lambda x: x["mtime"], reverse=True)


class DownloadWatcher:
    """폴링 기반 파일 감시 (카카오 inbox + 일반 Downloads)."""

    def __init__(self, dirs=None, callback=None, poll_interval: int = 15,
                 ignore_initial: bool = True):
        # 표준 카카오 inbox 폴더 자동 생성
        KAKAOTALK_INBOX.mkdir(parents=True, exist_ok=True)
        KAKAOWORK_INBOX.mkdir(parents=True, exist_ok=True)

        self._dirs = dirs or DEFAULT_WATCH_DIRS
        self._callback = callback
        self._interval = poll_interval
        self._ignore_initial = ignore_initial
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._seen: set[str] = set()

    def start(self) -> None:
        # 시작 시점에 이미 있는 파일은 새 파일로 보지 않음
        if self._ignore_initial:
            self._seen = {f["path"] for f in scan_existing(self._dirs)}
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dl-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def scan_existing(self, age_hours: int | None = None) -> list[dict]:
        return scan_existing(self._dirs, age_hours=age_hours)

    def _run(self) -> None:
        while not self._stop.wait(timeout=self._interval):
            try:
                current = scan_existing(self._dirs)
                for f in current:
                    if f["path"] not in self._seen:
                        self._seen.add(f["path"])
                        if self._callback:
                            try:
                                self._callback(f)
                            except Exception:
                                pass
            except Exception:
                pass


# ── 채팅방 매핑 ─────────────────────────

def map_to_active_room(file_mtime: float, tolerance_seconds: int = 60) -> dict | None:
    """파일 수정 시간 ± tolerance 내에 활성이었던 카카오워크 채팅방 추정.

    카카오워크 ConversationListBox에서 같은 시간 last_time 매칭.
    카카오톡은 매핑 어려움 (DB 암호화).
    """
    try:
        from .mixins.kakaowork_mixin import KakaoworkMixin
    except Exception:
        return None

    try:
        kw = type("_Kw", (KakaoworkMixin,), {})()
        rooms = kw.kakaowork_list_rooms()
    except Exception:
        return None

    # 가장 최근 활성 + 미읽음 있는 방을 우선
    candidates = sorted(
        rooms,
        key=lambda r: (r.get("unread_count", 0) > 0, r.get("last_time", "")),
        reverse=True,
    )
    if candidates:
        return candidates[0]
    return None
