"""채팅방 구독 관리.

사용자가 지정한 방만 자동 수집. 비구독 방은 명령 시에만 1회성 수집.

설정 파일: data/kakao_inbox/subscriptions.json
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from .download_watcher import KAKAOTALK_INBOX

_SUB_FILE = KAKAOTALK_INBOX.parent / "subscriptions.json"
_LOCK = threading.RLock()


def _load() -> dict:
    if not _SUB_FILE.exists():
        return {"version": 1, "subscriptions": {}}
    try:
        return json.loads(_SUB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "subscriptions": {}}


def _save(data: dict) -> None:
    _SUB_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SUB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def list_subscriptions() -> list[dict]:
    """전체 구독 목록 반환."""
    with _LOCK:
        data = _load()
        return list(data.get("subscriptions", {}).values())


def is_subscribed(room_name: str, app: str = "kakaowork") -> bool:
    """해당 채팅방이 구독 상태인지."""
    if not room_name:
        return False
    with _LOCK:
        subs = _load().get("subscriptions", {})
        key = f"{app}:{room_name}"
        sub = subs.get(key)
        return bool(sub and sub.get("active", True))


def subscribe(room_name: str, app: str = "kakaowork",
              collect_files: bool = True,
              collect_messages: bool = True,
              note: str = "") -> dict:
    """채팅방 구독 추가/갱신."""
    with _LOCK:
        data = _load()
        subs = data.setdefault("subscriptions", {})
        key = f"{app}:{room_name}"
        entry = {
            "app": app,
            "room": room_name,
            "active": True,
            "collect_files": collect_files,
            "collect_messages": collect_messages,
            "note": note,
            "created_at": subs.get(key, {}).get("created_at",
                                                 datetime.utcnow().isoformat()),
            "updated_at": datetime.utcnow().isoformat(),
        }
        subs[key] = entry
        _save(data)
        return entry


def unsubscribe(room_name: str, app: str = "kakaowork") -> bool:
    """구독 해제."""
    with _LOCK:
        data = _load()
        subs = data.get("subscriptions", {})
        key = f"{app}:{room_name}"
        if key in subs:
            del subs[key]
            _save(data)
            return True
        return False


def set_active(room_name: str, active: bool, app: str = "kakaowork") -> bool:
    """구독 일시 중지/재개."""
    with _LOCK:
        data = _load()
        subs = data.get("subscriptions", {})
        key = f"{app}:{room_name}"
        if key in subs:
            subs[key]["active"] = active
            subs[key]["updated_at"] = datetime.utcnow().isoformat()
            _save(data)
            return True
        return False
