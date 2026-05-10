"""카카오 로컬 데몬 → 서버 수신 라우터.

엔드포인트:
  POST /api/v1/kakao/event      — 로컬 데몬이 이벤트 전송
  GET  /api/v1/kakao/status     — 데몬 마지막 heartbeat 확인
  GET  /api/v1/kakao/rooms      — 카카오워크 채팅방 최신 목록
  GET  /api/v1/kakao/downloads  — 최근 감지된 파일 목록
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
kakao_router = APIRouter(prefix="/kakao", tags=["kakao"])

# ── 인메모리 상태 저장소 (재시작 시 초기화) ──
_state: dict[str, Any] = {
    "last_heartbeat": None,
    "daemon_version": None,
    "kakaowork_rooms": [],
    "kakaowork_unread": [],
    "recent_downloads": [],
    "events": [],          # 최근 100개 이벤트
}
_MAX_EVENTS = 100


# ── 모델 ──

class KakaoEvent(BaseModel):
    event_type: str          # "heartbeat" | "unread" | "file_downloaded" | "rooms_updated"
    app: str                 # "kakaowork" | "kakaotalk"
    timestamp: str
    payload: dict = {}


class DaemonStatus(BaseModel):
    online: bool
    last_heartbeat: str | None
    daemon_version: str | None
    kakaowork_room_count: int
    unread_count: int
    recent_download_count: int


# ── 엔드포인트 ──

@kakao_router.post("/event")
async def receive_event(event: KakaoEvent):
    """로컬 데몬이 이벤트를 전송하는 엔드포인트."""
    ev = event.model_dump()
    ev["received_at"] = datetime.utcnow().isoformat()

    _state["events"].append(ev)
    if len(_state["events"]) > _MAX_EVENTS:
        _state["events"] = _state["events"][-_MAX_EVENTS:]

    match event.event_type:
        case "heartbeat":
            _state["last_heartbeat"] = event.timestamp
            _state["daemon_version"] = event.payload.get("version")

        case "rooms_updated":
            if event.app == "kakaowork":
                _state["kakaowork_rooms"] = event.payload.get("rooms", [])
                _state["kakaowork_unread"] = [
                    r for r in _state["kakaowork_rooms"] if r.get("unread_count", 0) > 0
                ]
                logger.info("카카오워크 채팅방 업데이트: %d개 (미읽음 %d개)",
                            len(_state["kakaowork_rooms"]),
                            len(_state["kakaowork_unread"]))

        case "file_downloaded":
            dl = event.payload
            _state["recent_downloads"].insert(0, dl)
            _state["recent_downloads"] = _state["recent_downloads"][:100]
            logger.info("파일 수집: [%s] %s (%s) room=%s",
                        dl.get("source", "?"), dl.get("name"),
                        dl.get("category"), dl.get("room") or "-")

        case "unread":
            rooms = event.payload.get("rooms", [])
            logger.info("미읽음 알림: %s", [r.get("name") for r in rooms])

    return {"ok": True, "event_type": event.event_type}


@kakao_router.get("/status", response_model=DaemonStatus)
async def get_status():
    """데몬 온라인 상태 확인."""
    last = _state["last_heartbeat"]
    online = False
    if last:
        try:
            dt = datetime.fromisoformat(last)
            now = datetime.now(timezone.utc) if dt.tzinfo else datetime.utcnow()
            diff = (now - dt).total_seconds()
            online = diff < 120  # 2분 이내면 온라인
        except Exception:
            pass

    return DaemonStatus(
        online=online,
        last_heartbeat=last,
        daemon_version=_state["daemon_version"],
        kakaowork_room_count=len(_state["kakaowork_rooms"]),
        unread_count=len(_state["kakaowork_unread"]),
        recent_download_count=len(_state["recent_downloads"]),
    )


@kakao_router.get("/rooms")
async def get_rooms():
    """카카오워크 채팅방 최신 목록."""
    return {
        "rooms": _state["kakaowork_rooms"],
        "unread": _state["kakaowork_unread"],
        "updated_at": _state["last_heartbeat"],
    }


@kakao_router.get("/downloads")
async def get_downloads(limit: int = 20,
                        source: str | None = None,
                        category: str | None = None,
                        room: str | None = None):
    """최근 감지된 파일 목록 (필터 지원).

    source: kakaotalk | kakaowork | general
    category: image | document | video | audio | archive | other
    room: 채팅방 이름 (부분 일치)
    """
    files = _state["recent_downloads"]
    if source:
        files = [f for f in files if f.get("source") == source]
    if category:
        files = [f for f in files if f.get("category") == category]
    if room:
        files = [f for f in files if room.lower() in (f.get("room") or "").lower()]
    return {
        "files": files[:limit],
        "total": len(files),
        "filters": {"source": source, "category": category, "room": room},
    }


@kakao_router.get("/downloads/by-room")
async def get_downloads_by_room():
    """채팅방별 그룹화된 파일 카운트."""
    by_room: dict[str, dict] = {}
    for f in _state["recent_downloads"]:
        key = f.get("room") or "_unknown"
        if key not in by_room:
            by_room[key] = {"room": key, "count": 0, "by_category": {}}
        by_room[key]["count"] += 1
        cat = f.get("category", "other")
        by_room[key]["by_category"][cat] = by_room[key]["by_category"].get(cat, 0) + 1
    return {"rooms": list(by_room.values())}


@kakao_router.get("/events")
async def get_events(limit: int = 50):
    """최근 이벤트 로그."""
    return {"events": _state["events"][-limit:]}
