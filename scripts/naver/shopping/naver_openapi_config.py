"""네이버 검색 OpenAPI 연동 설정.

원칙:
- client_id / client_secret 은 환경변수에서만 로드. 하드코딩 금지.
- 누락 시 키 이름만 알린다 (값 노출 금지).
- DRY_RUN 기본값 True. 실제 호출은 명시적 false 전환 필요.
- 본 모듈은 비로그인 공개 검색 API 전용. 사용자 동의/OAuth/세션 흐름 없음.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_BASE_URL = "NAVER_OPENAPI_BASE_URL"
ENV_CLIENT_ID = "NAVER_OPENAPI_CLIENT_ID"
ENV_CLIENT_SECRET = "NAVER_OPENAPI_CLIENT_SECRET"
ENV_DRY_RUN = "NAVER_OPENAPI_DRY_RUN"

DEFAULT_BASE_URL = "https://openapi.naver.com"

REQUIRED_KEYS_FOR_LIVE = (
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
)


class NaverOpenApiConfigError(Exception):
    """설정 누락/형식 오류. 메시지에 비밀값 원문 금지."""


@dataclass(frozen=True)
class NaverOpenApiConfig:
    base_url: str
    client_id: str
    client_secret: str
    dry_run: bool

    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def redacted(self) -> dict:
        def _mask(v: str) -> str:
            return f"***len={len(v)}" if v else ""

        return {
            "base_url": self.base_url,
            "client_id": _mask(self.client_id),
            "client_secret": _mask(self.client_secret),
            "dry_run": self.dry_run,
        }


def _to_bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env: dict | None = None) -> NaverOpenApiConfig:
    src = env if env is not None else os.environ
    return NaverOpenApiConfig(
        base_url=(src.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URL,
        client_id=(src.get(ENV_CLIENT_ID) or "").strip(),
        client_secret=(src.get(ENV_CLIENT_SECRET) or "").strip(),
        dry_run=_to_bool(src.get(ENV_DRY_RUN), default=True),
    )


def require_live(cfg: NaverOpenApiConfig) -> None:
    """live 호출 직전 검증. 누락된 키 이름만 알려준다."""
    missing = []
    if not cfg.client_id:
        missing.append(ENV_CLIENT_ID)
    if not cfg.client_secret:
        missing.append(ENV_CLIENT_SECRET)
    if missing:
        raise NaverOpenApiConfigError("Naver OpenAPI live 호출에 필요한 환경변수 누락: " + ", ".join(missing))


__all__ = [
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
    "ENV_CLIENT_ID",
    "ENV_CLIENT_SECRET",
    "ENV_DRY_RUN",
    "REQUIRED_KEYS_FOR_LIVE",
    "NaverOpenApiConfig",
    "NaverOpenApiConfigError",
    "load_config",
    "require_live",
]
