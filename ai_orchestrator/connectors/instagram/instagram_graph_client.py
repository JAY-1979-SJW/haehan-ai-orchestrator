"""Instagram Graph API 클라이언트 (Instagram API with Instagram Login 방식).

apps/ig-comment-dm-bot/connectors/ig_api.py 의 로직을 포팅 + 확장:
- API 버전 하드코딩 제거 -> META_API_VERSION 환경변수
- Meta 에러코드/서브코드 파싱 (retryable 판단용)
- Private Reply 응답에서 recipient_id/message_id 추출

책임 분리 원칙(지시문 §38): 이 파일 밖에서 직접 httpx/requests 호출하지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

_TIMEOUT = 15

# Meta 에러코드 중 안전하게 재시도 가능한 것으로 분류하는 후보만 명시적으로 나열한다.
# 확실하지 않은 코드는 보수적으로 retryable=False (UNVERIFIED: Meta 정책은 실제 응답으로 계속 보정 필요).
_RETRYABLE_ERROR_CODES = {1, 2}  # 1=API Unknown, 2=API Service(임시 서버 오류) — UNVERIFIED
_RATE_LIMIT_ERROR_CODES = {4, 17, 32, 613}  # UNVERIFIED — Meta 문서 기준 rate-limit 계열 후보


def _api_version() -> str:
    return os.environ.get("META_API_VERSION", "v21.0").strip() or "v21.0"


def _base_url() -> str:
    return f"https://graph.instagram.com/{_api_version()}"


class InstagramApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: int | None = None,
        error_subcode: int | None = None,
        error_message: str | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.error_code = error_code
        self.error_subcode = error_subcode
        self.error_message = error_message
        self.retryable = retryable


@dataclass
class PrivateReplyResult:
    success: bool
    recipient_id: str | None = None
    message_id: str | None = None
    http_status: int | None = None
    error_code: int | None = None
    error_subcode: int | None = None
    error_message: str | None = None
    retryable: bool = False


def _request(method: str, path: str, token: str, **kwargs) -> dict[str, Any]:
    url = f"{_base_url()}/{path}"
    params = kwargs.pop("params", {})
    params["access_token"] = token
    resp = requests.request(method, url, params=params, timeout=_TIMEOUT, **kwargs)
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        err = body.get("error", {}) if isinstance(body, dict) else {}
        code = err.get("code")
        subcode = err.get("error_subcode")
        msg = err.get("message", str(body))
        retryable = code in _RETRYABLE_ERROR_CODES or code in _RATE_LIMIT_ERROR_CODES
        raise InstagramApiError(
            f"Graph API 오류({resp.status_code}): {msg}",
            http_status=resp.status_code,
            error_code=code,
            error_subcode=subcode,
            error_message=msg,
            retryable=retryable,
        )
    return body


def build_authorize_url(*, app_id: str, redirect_uri: str, state: str, scopes: list[str]) -> str:
    """Instagram Login 인가 URL 생성 (graph.facebook.com이 아니라 instagram.com 도메인 사용)."""
    scope_param = ",".join(scopes)
    return (
        "https://www.instagram.com/oauth/authorize"
        f"?client_id={app_id}&redirect_uri={redirect_uri}&response_type=code"
        f"&scope={scope_param}&state={state}"
    )


def exchange_code_for_short_lived_token(
    *, app_id: str, app_secret: str, redirect_uri: str, code: str
) -> dict[str, Any]:
    """Authorization code -> 단기 토큰. api.instagram.com (graph.instagram.com이 아님 — Meta 문서 기준)."""
    resp = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=_TIMEOUT,
    )
    body = resp.json()
    if resp.status_code >= 400:
        raise InstagramApiError(f"OAuth code 교환 실패({resp.status_code}): {body}", http_status=resp.status_code)
    return body


def exchange_for_long_lived_token(*, app_secret: str, short_lived_token: str) -> dict[str, Any]:
    resp = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_lived_token,
        },
        timeout=_TIMEOUT,
    )
    body = resp.json()
    if resp.status_code >= 400:
        raise InstagramApiError(f"장기 토큰 교환 실패({resp.status_code}): {body}", http_status=resp.status_code)
    return body


def verify_token(ig_user_id: str, token: str) -> dict[str, Any]:
    """토큰 유효성 + 계정 정보 확인."""
    return _request("GET", ig_user_id, token, params={"fields": "id,username,account_type"})


def get_recent_media(ig_user_id: str, token: str, limit: int = 10) -> list[dict[str, Any]]:
    body = _request(
        "GET",
        f"{ig_user_id}/media",
        token,
        params={"fields": "id,caption,timestamp,media_type,media_url,permalink", "limit": limit},
    )
    return body.get("data", [])


def get_comments(media_id: str, token: str) -> list[dict[str, Any]]:
    body = _request(
        "GET",
        f"{media_id}/comments",
        token,
        params={"fields": "id,text,username,timestamp"},
    )
    return body.get("data", [])


def send_private_reply(ig_user_id: str, comment_id: str, message_text: str, token: str) -> PrivateReplyResult:
    """댓글에 대한 비공개 답장(DM). 댓글 작성 후 7일 이내, 댓글당 1회만 가능(Meta 정책, UNVERIFIED 세부수치는
    실제 응답으로 계속 검증). 이 함수는 dedup을 하지 않는다 — 호출 전 반드시 상위에서 reply slot을 예약할 것."""
    try:
        body = _request(
            "POST",
            f"{ig_user_id}/messages",
            token,
            json={"recipient": {"comment_id": comment_id}, "message": {"text": message_text}},
        )
        return PrivateReplyResult(
            success=True,
            recipient_id=body.get("recipient_id"),
            message_id=body.get("message_id"),
            http_status=200,
        )
    except InstagramApiError as e:
        return PrivateReplyResult(
            success=False,
            http_status=e.http_status,
            error_code=e.error_code,
            error_subcode=e.error_subcode,
            error_message=e.error_message,
            retryable=e.retryable,
        )
    except requests.RequestException as e:
        return PrivateReplyResult(success=False, error_message=str(e), retryable=True)
