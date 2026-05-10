"""카카오톡 대화 내보내기 파일 파서 + 감시."""
from __future__ import annotations

import re
import time
from pathlib import Path

DEFAULT_SEARCH_DIRS = [
    Path.home() / "Downloads",
    Path.home() / "Documents" / "KakaoTalk Downloads",
    Path.home() / "OneDrive" / "Downloads",
    Path.home() / "바탕 화면",
    Path.home() / "Desktop",
]

_DATE_HEADER = re.compile(r"^(\d{4})년\s+(\d{1,2})월\s+(\d{1,2})일")
_MSG_LINE = re.compile(
    r"^\[(.+?)\]\s+\[(오전|오후)\s+(\d{1,2}):(\d{2})\]\s+(.*)"
)
_ROOM_HEADER = re.compile(r"^대화 상대\s*[:﹕]\s*(.+)$")
_SAVED_AT = re.compile(r"^저장한 날짜\s*[:﹕]\s*(.+)$")


def find_export_files(dirs=None) -> list[Path]:
    """KakaoTalk*.txt 파일 탐색 (최신순)."""
    if dirs is None:
        dirs = DEFAULT_SEARCH_DIRS
    found: list[Path] = []
    for d in dirs:
        try:
            found.extend(d.glob("KakaoTalk*.txt"))
        except Exception:
            pass
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def latest_export(dirs=None) -> Path | None:
    files = find_export_files(dirs)
    return files[0] if files else None


def parse_export_file(path: Path) -> dict:
    """대화 내보내기 텍스트 파일 파싱.

    반환: {room_name, saved_at, messages: [{date, sender, am_pm, hour, minute, text}]}
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e:
        return {"error": str(e), "messages": []}

    lines = text.splitlines()
    room_name = ""
    saved_at = ""
    messages: list[dict] = []
    current_date = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = _ROOM_HEADER.match(line)
        if m:
            room_name = m.group(1).strip()
            continue

        m = _SAVED_AT.match(line)
        if m:
            saved_at = m.group(1).strip()
            continue

        m = _DATE_HEADER.match(line)
        if m:
            current_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            continue

        m = _MSG_LINE.match(line)
        if m:
            sender, am_pm, hour_s, minute_s, text = m.groups()
            hour = int(hour_s)
            minute = int(minute_s)
            if am_pm == "오후" and hour != 12:
                hour += 12
            elif am_pm == "오전" and hour == 12:
                hour = 0
            messages.append({
                "date": current_date,
                "sender": sender.strip(),
                "time": f"{hour:02d}:{minute:02d}",
                "text": text,
            })

    return {"room_name": room_name, "saved_at": saved_at, "messages": messages}


def watch_for_new_export(callback, dirs=None, poll_interval: int = 10) -> None:
    """새 export 파일 감지 시 callback(path) 호출 (폴링, 블로킹)."""
    if dirs is None:
        dirs = DEFAULT_SEARCH_DIRS
    seen: set[Path] = set(find_export_files(dirs))
    while True:
        time.sleep(poll_interval)
        current = set(find_export_files(dirs))
        new_files = current - seen
        for p in sorted(new_files, key=lambda f: f.stat().st_mtime):
            try:
                callback(p)
            except Exception:
                pass
        seen = current
