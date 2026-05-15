"""응답 봉투 thin adapter.

기존 endpoint의 dict 반환값을 ApiResponse로 감싸거나,
향후 신규 endpoint에서 ApiResponse를 직접 반환할 때 사용한다.

기존 endpoint에는 아직 적용하지 않는다 (LEGACY_UI_DEPENDENT 보호).
다음 API_CONTRACT 공정에서 신규/내부 endpoint에 적용한다.
"""
from __future__ import annotations

from typing import Any, Optional

from .response_envelope import ApiError, ApiMeta, ApiResponse, api_error, api_success


def wrap_legacy_dict(
    data: dict[str, Any],
    meta: Optional[ApiMeta] = None,
) -> ApiResponse:
    """기존 dict 반환값을 ApiResponse.data로 감싼다.

    기존 key 구조는 data 안에 그대로 보존된다.
    endpoint 응답 형식이 변경될 경우에만 사용한다.
    """
    return api_success(data=data, meta=meta)


def wrap_legacy_list(
    items: list[Any],
    total: Optional[int] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> ApiResponse:
    """기존 list 반환값을 ApiResponse.data로 감싼다."""
    meta = None
    if any(v is not None for v in (total, page, page_size)):
        meta = ApiMeta(
            total=total if total is not None else len(items),
            page=page,
            page_size=page_size,
        )
    return api_success(data=items, meta=meta)


def wrap_http_exception(
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    meta: Optional[ApiMeta] = None,
) -> ApiResponse:
    """HTTPException detail을 ApiResponse.error로 변환한다."""
    return api_error(code=code, message=message, details=details, meta=meta)


__all__ = [
    "wrap_legacy_dict",
    "wrap_legacy_list",
    "wrap_http_exception",
    "api_success",
    "api_error",
    "ApiResponse",
    "ApiError",
    "ApiMeta",
]
