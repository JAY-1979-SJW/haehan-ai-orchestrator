"""공통 API 응답 봉투 타입.

기존 endpoint 응답 형식은 이 파일 추가로 변경하지 않는다.
다음 API_CONTRACT 공사 단계에서 실제 endpoint에 적용한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiMeta(BaseModel):
    request_id: str | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class ApiResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: ApiError | None = None
    meta: ApiMeta | None = None


def api_success(
    data: Any = None,
    meta: ApiMeta | None = None,
) -> ApiResponse:
    return ApiResponse(success=True, data=data, meta=meta)


def api_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    meta: ApiMeta | None = None,
) -> ApiResponse:
    return ApiResponse(
        success=False,
        error=ApiError(code=code, message=message, details=details),
        meta=meta,
    )
