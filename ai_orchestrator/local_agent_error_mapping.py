"""로컬 에이전트 에러 타입 및 응답 빌더.

에러 타입과 HTTP 상태 코드의 매핑, 표준화된 에러 응답 생성을 중앙화한다.
"""
from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    """로컬 에이전트 에러 타입."""
    INVALID_ALLOWED_ACTIONS = "INVALID_ALLOWED_ACTIONS"
    INVALID_TTL = "INVALID_TTL"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    INVALID_REGISTRATION_CODE = "INVALID_REGISTRATION_CODE"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    MISSING_URL = "MISSING_URL"
    URL_SCHEME_NOT_ALLOWED = "URL_SCHEME_NOT_ALLOWED"


# ── 에러 타입별 HTTP 상태 코드 매핑 ────────────────────────────────────────

ERROR_STATUS_CODES = {
    ErrorType.INVALID_ALLOWED_ACTIONS: 400,
    ErrorType.INVALID_TTL: 400,
    ErrorType.INVALID_REQUEST: 400,
    ErrorType.NOT_FOUND: 404,
    ErrorType.INVALID_REGISTRATION_CODE: 400,
    ErrorType.AGENT_NOT_FOUND: 404,
    ErrorType.UNKNOWN_ACTION: 400,
    ErrorType.MISSING_URL: 400,
    ErrorType.URL_SCHEME_NOT_ALLOWED: 400,
}


# ── 에러 응답 생성 헬퍼 ────────────────────────────────────────────────────

def make_error_response(
    error_type: ErrorType,
    message: str | None = None,
    error_code: str | None = None
) -> tuple[int, dict]:
    """표준화된 에러 응답 생성.

    Args:
        error_type: ErrorType enum 값
        message: 에러 메시지 (기본값: 에러 타입명)
        error_code: 사용자 정의 에러 코드 (생략 시 error_type.value 사용)

    Returns: (http_status_code, detail_dict)
    """
    status_code = ERROR_STATUS_CODES.get(error_type, 400)

    if message is None:
        message = error_type.value

    if error_code is None:
        error_code = error_type.value

    detail = {
        "code": error_code,
        "message": message,
    }

    return status_code, detail
