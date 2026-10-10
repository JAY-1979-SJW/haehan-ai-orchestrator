"""
카카오워크 Bot webhook 수신 → 메시지 파싱 모듈
공식 Bot/Web API (https://docs.kakaowork.com/reference) 범위 내에서만 구현.

동작 방식:
  카카오워크 봇이 메시지를 수신하면 등록된 webhook URL로 HTTP POST를 전송.
  이 모듈은 해당 payload를 파싱해 inbox 저장 형식으로 변환하는 역할만 수행.
  자동 회신 없음, 수집만 수행.

환경변수:
  KAKAOWORK_BOT_KEY   — 카카오워크 봇 키 (webhook 검증용, 선택)
  KAKAOWORK_CHANNEL   — 봇이 속한 채널/팀 식별자 (source_account로 사용)
"""

import hashlib
import os
from datetime import UTC, datetime

from orchestrator_v1.core.logger import get_logger

log = get_logger("kakaowork_reader")

_KAKAOWORK_CHANNEL = os.environ.get("KAKAOWORK_CHANNEL", "kakaowork-default")

# 카카오워크 Bot webhook 이벤트 타입 (공식 문서 기준)
_SUPPORTED_EVENT_TYPES = {"message", "action"}


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _build_external_id(message_id: str, channel_id: str = "") -> str:
    """카카오워크 메시지 고유 ID 생성. message_id 우선, 없으면 hash 기반."""
    if message_id:
        return f"kakaowork:{message_id}"
    raw = f"{channel_id}:{_now_iso()}"
    return f"kakaowork:hash:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _parse_received_at(created_at_ms: int | None) -> str:
    """카카오워크 timestamp(ms) → ISO 형식 변환."""
    if created_at_ms:
        try:
            ts = int(created_at_ms) / 1000
            return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, OSError):
            pass
    return _now_iso()


def parse_webhook_payload(payload: dict) -> dict:
    """
    카카오워크 Bot webhook payload를 inbox 저장 형식으로 변환.

    입력 payload 최소 구조 (공식 Bot API 기준):
    {
        "type": "message",
        "user_id": "user-123",
        "message": {
            "id": "msg-001",
            "text": "안녕하세요",
            "created_at": 1713751200000
        },
        "channel": { "id": "ch-001" }
    }

    반환:
    {
        "external_id": str,
        "source_type": "kakaowork",
        "source_account": str,
        "sender": str,
        "title": str,       — message text 앞 50자
        "body_raw": str,
        "received_at": str,
        "metadata": dict,
    }

    필수 필드 누락 시 ValueError 발생.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload는 dict이어야 합니다")

    event_type = payload.get("type", "")
    if not event_type:
        raise ValueError("payload.type 누락")

    message = payload.get("message") or {}
    message_id = str(message.get("id", ""))
    text = str(message.get("text") or "").strip()
    created_at_ms = message.get("created_at")

    user_id = str(payload.get("user_id") or payload.get("user_key") or "")
    if not user_id:
        raise ValueError("payload.user_id 또는 user_key 누락")

    channel = payload.get("channel") or {}
    channel_id = str(channel.get("id", ""))

    source_account = os.environ.get("KAKAOWORK_CHANNEL", _KAKAOWORK_CHANNEL)
    external_id = _build_external_id(message_id, channel_id)
    received_at = _parse_received_at(created_at_ms)

    title = (text[:50] + "...") if len(text) > 50 else (text or f"[{event_type}]")

    return {
        "external_id": external_id,
        "source_type": "kakaowork",
        "source_account": source_account,
        "sender": user_id,
        "title": title,
        "body_raw": text,
        "received_at": received_at,
        "metadata": {
            "event_type": event_type,
            "channel_id": channel_id,
            "message_id": message_id,
            "user_id": user_id,
        },
    }
