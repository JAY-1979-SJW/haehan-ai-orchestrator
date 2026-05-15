"""공통 API 응답 봉투 타입.

기존 endpoint 응답 형식은 이 파일 추가로 변경하지 않는다.
다음 API_CONTRACT 공사 단계에서 실제 endpoint에 적용한다.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ApiMeta(BaseModel):
    request_id: Optional[str] = None
    total: Optional[int] = None
    page: Optional[int] = None
    page_size: Optional[int] = None


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[ApiError] = None
    meta: Optional[ApiMeta] = None


def api_success(
    data: Any = None,
    meta: Optional[ApiMeta] = None,
) -> ApiResponse:
    return ApiResponse(success=True, data=data, meta=meta)


def api_error(
    code: str,
    message: str,
    details: Optional[dict[str, Any]] = None,
    meta: Optional[ApiMeta] = None,
) -> ApiResponse:
    return ApiResponse(
        success=False,
        error=ApiError(code=code, message=message, details=details),
        meta=meta,
    )
