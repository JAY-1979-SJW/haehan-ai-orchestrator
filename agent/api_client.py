"""서버 API 클라이언트 (B안 3단계 HTTP 폴링).

stdlib ``urllib`` 만 사용해 외부 의존성을 늘리지 않는다.
모든 실패 케이스는 예외를 삼키고 ``err_code`` 문자열로 축약해 반환한다
— 루프가 다음 poll 주기까지 살아남아야 하므로 crash 금지.

Endpoint 계약:
    GET  {api_url}/tasks/poll
        → 200 + JSON. 빈 큐: ``{}`` 또는 ``null`` 또는 ``{"task": null}``.
           실행 대상: ``{"task": {...}}`` 또는 task dict 자체 (``action`` 키 포함).
    POST {api_url}/tasks/result
        → 2xx 면 성공. body 는 execute_task 결과 dict 그대로.

인증:
    모든 요청에 ``Authorization: Bearer <token>``. token 이 비어 있으면
    헤더 자체를 생략해 anonymous 개발 서버와도 호환되도록 한다.
"""
from __future__ import annotations

import json
import logging
from typing import Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0

# api_client 로컬 에러 코드 — agent.errors 체계와 분리.
API_UNREACHABLE = "api_unreachable"
API_AUTH_FAILED = "api_auth_failed"
API_BAD_RESPONSE = "api_bad_response"
API_SERVER_ERROR = "api_server_error"


def _headers(token: str) -> dict:
    h = {"Content-Type": "application/json",
         "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _classify_http_error(code: int) -> str:
    if code in (401, 403):
        return API_AUTH_FAILED
    if 500 <= code <= 599:
        return API_SERVER_ERROR
    return API_BAD_RESPONSE


def fetch_task(
    api_url: str, token: str, *, timeout: float = TIMEOUT_SECONDS,
) -> Tuple[Optional[dict], Optional[str]]:
    """GET /tasks/poll — task 한 건을 반환하거나 빈 큐/에러를 구분.

    Returns:
        (task_dict, None)   실행 대상이 있음
        (None, None)        빈 큐 (정상)
        (None, err_code)    네트워크/인증/스키마 실패
    """
    if not isinstance(api_url, str) or not api_url.strip():
        return None, API_BAD_RESPONSE
    url = f"{api_url.rstrip('/')}/tasks/poll"
    req = urllib_request.Request(url, headers=_headers(token), method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib_error.HTTPError as e:
        return None, _classify_http_error(e.code)
    except urllib_error.URLError as e:
        logger.info("fetch_task unreachable: %s", e)
        return None, API_UNREACHABLE
    except TimeoutError:
        return None, API_UNREACHABLE

    try:
        text = body.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, API_BAD_RESPONSE
    if not text:
        return None, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None, API_BAD_RESPONSE

    # 빈 큐를 표현하는 여러 변형을 모두 수용
    if payload is None or payload == {} or payload == []:
        return None, None
    if not isinstance(payload, dict):
        return None, API_BAD_RESPONSE

    wrapped = payload.get("task")
    if wrapped is None:
        # {"task": null} → 빈 큐 / 혹은 task dict 자체가 payload 인 경우
        if isinstance(payload.get("action"), str) and payload.get("action"):
            return payload, None
        return None, None
    if isinstance(wrapped, dict):
        return wrapped, None
    return None, API_BAD_RESPONSE


def report_result(
    api_url: str, token: str, result: dict,
    *, timeout: float = TIMEOUT_SECONDS,
) -> Optional[str]:
    """POST /tasks/result. 성공 시 None, 실패 시 err_code 반환."""
    if not isinstance(api_url, str) or not api_url.strip():
        return API_BAD_RESPONSE
    url = f"{api_url.rstrip('/')}/tasks/result"
    try:
        body = json.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return API_BAD_RESPONSE
    req = urllib_request.Request(
        url, data=body, headers=_headers(token), method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
    except urllib_error.HTTPError as e:
        return _classify_http_error(e.code)
    except urllib_error.URLError as e:
        logger.info("report_result unreachable: %s", e)
        return API_UNREACHABLE
    except TimeoutError:
        return API_UNREACHABLE
    if 200 <= status < 300:
        return None
    return API_BAD_RESPONSE


__all__ = [
    "fetch_task",
    "report_result",
    "TIMEOUT_SECONDS",
    "API_UNREACHABLE",
    "API_AUTH_FAILED",
    "API_BAD_RESPONSE",
    "API_SERVER_ERROR",
]
