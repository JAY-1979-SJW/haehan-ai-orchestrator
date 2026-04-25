"""YouTube Data API v3 설정 로더 (F-4S-3, read-only PoC).

원칙:
- API key 는 환경변수에서만 로드. 하드코딩/문서/로그 출력 금지.
- 누락 시 키 존재 여부 / 길이만 노출. 원문 secret 노출 금지.
- 본 모듈은 read-only PoC 전용. OAuth / 업로드 / 수정 / 삭제 / 댓글 작성 흐름 없음.
- requests 신규 의존성 없음 (호출 측에서 stdlib urllib 사용).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


ENV_API_KEY = "YOUTUBE_DATA_API_KEY"
ENV_BASE_URL = "YOUTUBE_DATA_API_BASE_URL"
ENV_TIMEOUT_SECONDS = "YOUTUBE_DATA_API_TIMEOUT_SECONDS"

DEFAULT_BASE_URL = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class YoutubeDataApiConfig:
    api_key: Optional[str]
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def live_enabled(self) -> bool:
        return bool(self.api_key)

    def redacted(self) -> Dict[str, Any]:
        return {
            "api_key_present": bool(self.api_key),
            "api_key_length": len(self.api_key) if self.api_key else 0,
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


def load_youtube_data_api_config(env: Optional[Dict[str, str]] = None) -> YoutubeDataApiConfig:
    src = env if env is not None else os.environ
    api_key = _strip_or_none(src.get(ENV_API_KEY))
    base_url = _strip_or_none(src.get(ENV_BASE_URL)) or DEFAULT_BASE_URL
    timeout_seconds = _parse_timeout(src.get(ENV_TIMEOUT_SECONDS))
    return YoutubeDataApiConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
    )
