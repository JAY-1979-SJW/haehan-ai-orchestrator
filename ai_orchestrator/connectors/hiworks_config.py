"""Hiworks 공식 API 연동용 설정 로더.

원칙:
- 자격증명/토큰은 환경변수에서만 읽고, 파일/소스에 하드코딩 금지.
- 누락 시 명확한 에러를 반환하되, 평문 값(시크릿)은 메시지에 포함하지 않는다.
- DRY_RUN 기본값은 True. 실제 호출이 필요한 경우에만 명시적으로 false 로 전환.
- Hiworks 공식 앱 등록(https://developers.hiworks.com 참고) 전 단계에서도
  코드가 import/검증만으로 깨지지 않도록 graceful fallback 을 제공한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# 환경변수 키 (값은 .env / 운영 시크릿 매니저에서 주입).
ENV_BASE_URL = "HIWORKS_BASE_URL"
ENV_CLIENT_ID = "HIWORKS_CLIENT_ID"
ENV_CLIENT_SECRET = "HIWORKS_CLIENT_SECRET"
ENV_OFFICE_TOKEN = "HIWORKS_OFFICE_TOKEN"
ENV_DRY_RUN = "HIWORKS_DRY_RUN"

# 공식 도메인 placeholder. 실제 값은 .env 로 주입.
DEFAULT_BASE_URL = "https://api.hiworks.com"

REQUIRED_KEYS_FOR_LIVE = (
    ENV_BASE_URL,
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
    ENV_OFFICE_TOKEN,
)


class HiworksConfigError(Exception):
    """설정 누락/형식 오류. 메시지에 비밀값 원문 금지."""


@dataclass(frozen=True)
class HiworksConfig:
    base_url: str
    client_id: str
    client_secret: str
    office_token: str
    dry_run: bool

    def has_credentials(self) -> bool:
        """live 호출 가능 여부 (모든 필수 값이 채워졌는지)."""
        return bool(self.base_url and self.client_id and self.client_secret and self.office_token)

    def redacted(self) -> dict:
        """로그/응답용 안전 표현 — 시크릿은 길이만 노출."""

        def _mask(v: str) -> str:
            if not v:
                return ""
            return f"***len={len(v)}"

        return {
            "base_url": self.base_url,
            "client_id": _mask(self.client_id),
            "client_secret": _mask(self.client_secret),
            "office_token": _mask(self.office_token),
            "dry_run": self.dry_run,
        }


def _to_bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def load_config(env: dict | None = None) -> HiworksConfig:
    """환경변수에서 Hiworks 설정을 로드한다.

    누락된 키가 있어도 즉시 실패시키지 않는다 (dry_run 기본 True).
    실제 호출 시점에 ``require_live(cfg)`` 로 강제 검증한다.
    """
    src = env if env is not None else os.environ
    return HiworksConfig(
        base_url=(src.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URL,
        client_id=(src.get(ENV_CLIENT_ID) or "").strip(),
        client_secret=(src.get(ENV_CLIENT_SECRET) or "").strip(),
        office_token=(src.get(ENV_OFFICE_TOKEN) or "").strip(),
        # 명시 설정이 없으면 안전한 기본값(dry_run=True).
        dry_run=_to_bool(src.get(ENV_DRY_RUN), default=True),
    )


def require_live(cfg: HiworksConfig) -> None:
    """실제 호출 직전에 호출. 누락된 키 이름만 알려준다 (값 노출 금지)."""
    missing = []
    if not cfg.base_url:
        missing.append(ENV_BASE_URL)
    if not cfg.client_id:
        missing.append(ENV_CLIENT_ID)
    if not cfg.client_secret:
        missing.append(ENV_CLIENT_SECRET)
    if not cfg.office_token:
        missing.append(ENV_OFFICE_TOKEN)
    if missing:
        raise HiworksConfigError("Hiworks live 호출에 필요한 환경변수 누락: " + ", ".join(missing))


__all__ = [
    "DEFAULT_BASE_URL",
    "ENV_BASE_URL",
    "ENV_CLIENT_ID",
    "ENV_CLIENT_SECRET",
    "ENV_DRY_RUN",
    "ENV_OFFICE_TOKEN",
    "REQUIRED_KEYS_FOR_LIVE",
    "HiworksConfig",
    "HiworksConfigError",
    "load_config",
    "require_live",
]
