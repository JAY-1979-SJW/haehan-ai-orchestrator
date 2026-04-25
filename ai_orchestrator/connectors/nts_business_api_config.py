"""TAX-API-1 — 국세청 사업자등록정보 API (공공데이터포털) 설정.

본 모듈은 공공데이터포털 (data.go.kr) 의 "국세청 사업자등록정보 진위확인 및
상태조회" API 를 호출하기 위한 설정만 담는다. 비밀값은 환경변수에서만
로드하며, 평문이 로그/repr/redacted() 어디에도 노출되지 않는다.

원칙:
  - service_key 는 환경변수에서만 로드. 하드코딩 금지.
  - 누락 시 키 이름만 알린다 (값 노출 금지).
  - live_enabled 기본값 = (service_key 가 비어있지 않으면 True).
  - 본 모듈은 *공개 비로그인 API* 전용 — 사용자 동의/OAuth/세션 흐름 없음.
  - 어떤 경우에도 홈택스 화면/쿠키/storage_state 에 접근하지 않는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


# ─── 환경변수 키 ────────────────────────────────────────────────────────────

# 1순위 — 본 PoC 전용 키 이름.
ENV_SERVICE_KEY_PRIMARY = "NTS_BUSINESS_API_SERVICE_KEY"
# 2순위 — 프로젝트 차원의 공공데이터포털 공용 키 이름.
ENV_SERVICE_KEY_FALLBACK = "PUBLICDATA_SERVICE_KEY"

ENV_BASE_URL = "NTS_BUSINESS_API_BASE_URL"
ENV_TIMEOUT_SECONDS = "NTS_BUSINESS_API_TIMEOUT_SECONDS"

DEFAULT_BASE_URL = "https://api.odcloud.kr/api/nts-businessman/v1"
DEFAULT_TIMEOUT_SECONDS = 10.0

# 본 PoC 호출 한도 (api/odcloud 단일 호출 제한).
MAX_BATCH_SIZE = 100


class NtsBusinessApiConfigError(Exception):
    """설정 누락/형식 오류. 메시지에 비밀값 원문 금지."""


@dataclass(frozen=True)
class NtsBusinessApiConfig:
    service_key: Optional[str]
    base_url: str
    timeout_seconds: float
    live_enabled: bool
    service_key_source: str  # 어떤 env 키에서 왔는지 (값 자체는 아님).

    def has_credentials(self) -> bool:
        return bool(self.service_key)

    def redacted(self) -> dict:
        """진단/로그용. 키 원문은 절대 노출하지 않는다."""
        sk = self.service_key or ""
        return {
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "live_enabled": self.live_enabled,
            "service_key_present": bool(sk),
            "service_key_length": len(sk),
            "service_key_source": self.service_key_source,
        }


def _to_float(v: Optional[str], default: float, lo: float, hi: float) -> float:
    if v is None or not str(v).strip():
        return default
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return default
    if f < lo:
        return lo
    if f > hi:
        return hi
    return f


def _strip_or_empty(v: Optional[str]) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        return ""
    return v.strip()


def load_nts_business_api_config(
    env: Optional[dict] = None,
) -> NtsBusinessApiConfig:
    """환경변수에서 설정을 읽어 NtsBusinessApiConfig 를 반환.

    service_key 는 ``NTS_BUSINESS_API_SERVICE_KEY`` 우선, 없으면
    ``PUBLICDATA_SERVICE_KEY`` 를 사용한다. 둘 다 비어있으면
    ``live_enabled=False`` 로 fallback 한다 (FAIL 아님 — 설정만 비활성).
    """
    src = env if env is not None else os.environ

    primary = _strip_or_empty(src.get(ENV_SERVICE_KEY_PRIMARY))
    fallback = _strip_or_empty(src.get(ENV_SERVICE_KEY_FALLBACK))

    if primary:
        service_key: Optional[str] = primary
        source = ENV_SERVICE_KEY_PRIMARY
    elif fallback:
        service_key = fallback
        source = ENV_SERVICE_KEY_FALLBACK
    else:
        service_key = None
        source = ""

    base_url = _strip_or_empty(src.get(ENV_BASE_URL)) or DEFAULT_BASE_URL
    timeout_seconds = _to_float(
        src.get(ENV_TIMEOUT_SECONDS),
        default=DEFAULT_TIMEOUT_SECONDS,
        lo=1.0,
        hi=60.0,
    )

    return NtsBusinessApiConfig(
        service_key=service_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        live_enabled=bool(service_key),
        service_key_source=source,
    )


def require_live(cfg: NtsBusinessApiConfig) -> None:
    """live 호출 직전 검증. 누락된 키 이름만 알려준다 (값 미노출)."""
    if cfg.live_enabled and cfg.service_key:
        return
    raise NtsBusinessApiConfigError(
        "NTS Business API live 호출에 필요한 환경변수 누락: "
        f"{ENV_SERVICE_KEY_PRIMARY} (또는 {ENV_SERVICE_KEY_FALLBACK})"
    )


__all__ = [
    "ENV_SERVICE_KEY_PRIMARY",
    "ENV_SERVICE_KEY_FALLBACK",
    "ENV_BASE_URL",
    "ENV_TIMEOUT_SECONDS",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_BATCH_SIZE",
    "NtsBusinessApiConfig",
    "NtsBusinessApiConfigError",
    "load_nts_business_api_config",
    "require_live",
]
