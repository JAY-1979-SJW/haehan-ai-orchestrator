"""Instagram API (Instagram Login 방식) 얇은 래퍼 — 미디어/댓글 조회, 댓글에 대한 비공개 답장(DM) 발송.

이 앱은 최신 "Instagram API with Instagram Login" 방식으로 설정되어 있어(권한명이
instagram_business_* 이고 발급 토큰이 IGAA... 로 시작), graph.facebook.com이 아니라
graph.instagram.com 을 사용해야 한다 (구버전 Facebook 로그인 기반 Graph API와는 호스트가 다름).

DM 발송은 공식 'Private Replies' 기능(POST /{ig-user-id}/messages, recipient.comment_id)을 사용한다.
이 API 는 댓글 작성 후 7일 이내에만 응답 가능하다는 Meta 정책 제약이 있다.
"""

from __future__ import annotations

from typing import Any

import requests

_GRAPH_BASE = "https://graph.instagram.com/v21.0"
_TIMEOUT = 15


class IgApiError(Exception):
    def __init__(self, message: str, response_body: dict | None = None):
        super().__init__(message)
        self.response_body = response_body


def _request(method: str, path: str, token: str, **kwargs) -> dict[str, Any]:
    url = f"{_GRAPH_BASE}/{path}"
    params = kwargs.pop("params", {})
    params["access_token"] = token
    resp = requests.request(method, url, params=params, timeout=_TIMEOUT, **kwargs)
    body = resp.json()
    if resp.status_code >= 400:
        error_msg = body.get("error", {}).get("message", str(body))
        raise IgApiError(f"Graph API 오류({resp.status_code}): {error_msg}", response_body=body)
    return body


def get_recent_media(ig_user_id: str, token: str, limit: int = 10) -> list[dict[str, Any]]:
    """최근 게시물 목록 (id, caption, timestamp)."""
    body = _request(
        "GET",
        f"{ig_user_id}/media",
        token,
        params={"fields": "id,caption,timestamp", "limit": limit},
    )
    return body.get("data", [])


def get_comments(media_id: str, token: str) -> list[dict[str, Any]]:
    """특정 게시물의 댓글 목록 (id, text, username, timestamp)."""
    body = _request(
        "GET",
        f"{media_id}/comments",
        token,
        params={"fields": "id,text,username,timestamp"},
    )
    return body.get("data", [])


def send_private_reply(ig_user_id: str, comment_id: str, message_text: str, token: str) -> dict[str, Any]:
    """댓글에 대한 비공개 답장(DM) 발송. 댓글 작성 후 7일 이내에만 가능(Meta 정책)."""
    return _request(
        "POST",
        f"{ig_user_id}/messages",
        token,
        json={
            "recipient": {"comment_id": comment_id},
            "message": {"text": message_text},
        },
    )


def verify_token(ig_user_id: str, token: str) -> dict[str, Any]:
    """토큰 유효성 + 계정 정보 확인용 (설정 화면에서 '연결 테스트' 버튼에 사용)."""
    return _request("GET", ig_user_id, token, params={"fields": "id,username"})
