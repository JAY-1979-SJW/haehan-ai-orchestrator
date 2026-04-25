"""TAX-API-1 — NtsBusinessApiConfig 단위 테스트.

검증:
  - 키 없음 → live_enabled=False (예외 없이)
  - PRIMARY 우선, FALLBACK 차순
  - redacted() 에 service_key 원문 미노출
  - timeout 정규화
  - require_live 누락 시 키 이름만 알림
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ai_orchestrator.connectors.nts_business_api_config import (  # noqa: E402
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    ENV_BASE_URL,
    ENV_SERVICE_KEY_FALLBACK,
    ENV_SERVICE_KEY_PRIMARY,
    ENV_TIMEOUT_SECONDS,
    NtsBusinessApiConfigError,
    load_nts_business_api_config,
    require_live,
)


def test_load_no_keys_disables_live():
    cfg = load_nts_business_api_config(env={})
    assert cfg.service_key is None
    assert cfg.live_enabled is False
    assert cfg.has_credentials() is False
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert cfg.service_key_source == ""


def test_load_primary_key_preferred_over_fallback():
    cfg = load_nts_business_api_config(env={
        ENV_SERVICE_KEY_PRIMARY: "PRIMARY_KEY_VALUE",
        ENV_SERVICE_KEY_FALLBACK: "FALLBACK_KEY_VALUE",
    })
    assert cfg.service_key == "PRIMARY_KEY_VALUE"
    assert cfg.service_key_source == ENV_SERVICE_KEY_PRIMARY
    assert cfg.live_enabled is True


def test_load_fallback_used_when_primary_missing():
    cfg = load_nts_business_api_config(env={
        ENV_SERVICE_KEY_FALLBACK: "FALLBACK_KEY_VALUE",
    })
    assert cfg.service_key == "FALLBACK_KEY_VALUE"
    assert cfg.service_key_source == ENV_SERVICE_KEY_FALLBACK
    assert cfg.live_enabled is True


def test_load_strips_whitespace_and_treats_blank_as_missing():
    cfg = load_nts_business_api_config(env={
        ENV_SERVICE_KEY_PRIMARY: "   ",
        ENV_SERVICE_KEY_FALLBACK: "  REAL_KEY  ",
    })
    assert cfg.service_key == "REAL_KEY"
    assert cfg.service_key_source == ENV_SERVICE_KEY_FALLBACK


def test_redacted_does_not_leak_service_key_value():
    secret = "SUPER_SECRET_KEY_DO_NOT_LEAK"
    cfg = load_nts_business_api_config(env={
        ENV_SERVICE_KEY_PRIMARY: secret,
    })
    rd = cfg.redacted()
    serialized = repr(rd)
    assert secret not in serialized
    assert rd["service_key_present"] is True
    assert rd["service_key_length"] == len(secret)
    assert rd["service_key_source"] == ENV_SERVICE_KEY_PRIMARY


def test_redacted_when_no_key_present():
    cfg = load_nts_business_api_config(env={})
    rd = cfg.redacted()
    assert rd["service_key_present"] is False
    assert rd["service_key_length"] == 0
    assert rd["service_key_source"] == ""
    assert rd["live_enabled"] is False


def test_base_url_override_via_env():
    cfg = load_nts_business_api_config(env={
        ENV_BASE_URL: "https://example.invalid/api/x/v1",
    })
    assert cfg.base_url == "https://example.invalid/api/x/v1"


def test_timeout_seconds_clipped_to_range():
    cfg_low = load_nts_business_api_config(env={
        ENV_TIMEOUT_SECONDS: "0.1",
    })
    assert cfg_low.timeout_seconds == 1.0

    cfg_high = load_nts_business_api_config(env={
        ENV_TIMEOUT_SECONDS: "9999",
    })
    assert cfg_high.timeout_seconds == 60.0

    cfg_bad = load_nts_business_api_config(env={
        ENV_TIMEOUT_SECONDS: "not-a-number",
    })
    assert cfg_bad.timeout_seconds == DEFAULT_TIMEOUT_SECONDS

    cfg_ok = load_nts_business_api_config(env={
        ENV_TIMEOUT_SECONDS: "5.5",
    })
    assert cfg_ok.timeout_seconds == 5.5


def test_require_live_raises_when_disabled():
    cfg = load_nts_business_api_config(env={})
    with pytest.raises(NtsBusinessApiConfigError) as ei:
        require_live(cfg)
    msg = str(ei.value)
    assert ENV_SERVICE_KEY_PRIMARY in msg
    assert ENV_SERVICE_KEY_FALLBACK in msg
    # 메시지에는 키 원문이 들어갈 수 없다 (애초에 없으니까).
    assert "SUPER" not in msg


def test_require_live_passes_when_key_present():
    cfg = load_nts_business_api_config(env={
        ENV_SERVICE_KEY_PRIMARY: "x",
    })
    # 예외 없이 통과해야 한다.
    require_live(cfg)
