"""Instagram Webhook payload 파싱 — payload 구조 변경에 대비해 router/service와 분리.

인식 못하는 payload는 예외를 던지지 않고 None을 반환 -> 호출부가 raw event log에 저장한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ParsedCommentEvent:
    instagram_user_id: str  # webhook을 받은 우리 계정(entry.id)
    comment_id: str
    media_id: str | None
    media_product_type: str | None
    commenter_ig_scoped_id: str | None
    commenter_username: str | None
    comment_text: str | None
    comment_created_at: str | None


def parse_comment_events(payload: dict[str, Any]) -> list[ParsedCommentEvent]:
    """object == 'instagram' 이고 changes[].field == 'comments' 인 이벤트만 추출."""
    if payload.get("object") != "instagram":
        return []

    out: list[ParsedCommentEvent] = []
    for entry in payload.get("entry", []) or []:
        account_id = entry.get("id")
        for change in entry.get("changes", []) or []:
            if change.get("field") != "comments":
                continue
            value = change.get("value") or {}
            comment_id = value.get("id")
            if not account_id or not comment_id:
                continue
            from_obj = value.get("from") or {}
            media_obj = value.get("media") or {}
            out.append(
                ParsedCommentEvent(
                    instagram_user_id=str(account_id),
                    comment_id=str(comment_id),
                    media_id=media_obj.get("id"),
                    media_product_type=media_obj.get("media_product_type"),
                    commenter_ig_scoped_id=from_obj.get("id"),
                    commenter_username=from_obj.get("username"),
                    comment_text=value.get("text"),
                    comment_created_at=None,
                )
            )
    return out
