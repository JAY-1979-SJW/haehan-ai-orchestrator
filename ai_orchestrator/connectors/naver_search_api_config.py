"""Naver Search Open API 설정 로더 (F-4S-2).

원칙:
- client_id / client_secret 은 환경변수에서만 로드. 하드코딩 금지.
- 누락 시 키 이름/길이만 노출. 원문 secret 노출 금지.
- 본 모듈은 비로그인 공개 검색 API 전용. OAuth / 카페 가입 / 글쓰기 흐름 없음.
- requests 신규 의존성 없음 (호출 측에서 stdlib urllib 사용).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


ENV_CLIENT_ID = "NAVER_CLIENT_ID"
ENV_CLIENT_SECRET = "NAVER_CLIENT_SECRET"
ENV_BASE_URL = "NAVER_SEARCH_API_BASE_URL"
ENV_TIMEOUT_SECONDS = "NAVER_SEARCH_API_TIMEOUT_SECONDS"

DEFAULT_BASE_URL = "https://openapi.naver.com/v1/search"
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class NaverSearchApiConfig:
    client_id: Optional[str]
    client_secret: Optional[str]
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def live_enabled(self) -> bool:
        return bool(self.client_id) and bool(self.client_secret)

    def redacted(self) -> Dict[str, Any]:
        return {
            "client_id_present": bool(self.client_id),
            "client_secret_present": bool(self.client_secret),
            "client_id_length": len(self.client_id) if self.client_id else 0,
            "client_secret_length": len(self.client_secret) if self.client_secret else 0,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
        }


def _strip_or_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_timeout(raw: Optional[str]) -> float:
    if raw is None or not raw.strip():
        return DEFAULT_TIMEOUT_SECONDS
    try:
        parsed = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    if parsed <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return parsed


def load_naver_search_api_config(env: Optional[Dict[str, str]] = None) -> NaverSearchApiConfig:
    src = env if env is not None else os.environ
    client_id = _strip_or_none(src.get(ENV_CLIENT_ID))
    client_secret = _strip_or_none(src.get(ENV_CLIENT_SECRET))
    base_url = _strip_or_none(src.get(ENV_BASE_URL)) or DEFAULT_BASE_URL
    timeout_seconds = _parse_timeout(src.get(ENV_TIMEOUT_SECONDS))
    return NaverSearchApiConfig(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
    )
