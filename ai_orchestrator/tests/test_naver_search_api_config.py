"""Tests for ai_orchestrator/connectors/naver_search_api_config.py (F-4S-2)."""
from __future__ import annotations

import pytest

from ai_orchestrator.connectors import naver_search_api_config as cfg_mod


def _clear(monkeypatch):
    for k in (
        cfg_mod.ENV_CLIENT_ID,
        cfg_mod.ENV_CLIENT_SECRET,
        cfg_mod.ENV_BASE_URL,
        cfg_mod.ENV_TIMEOUT_SECONDS,
    ):
        monkeypatch.delenv(k, raising=False)


def test_load_returns_unconfigured_when_no_env(monkeypatch):
    _clear(monkeypatch)
    cfg = cfg_mod.load_naver_search_api_config(env={})
    assert cfg.client_id is None
    assert cfg.client_secret is None
    assert cfg.live_enabled is False


def test_live_enabled_only_when_both_present(monkeypatch):
    _clear(monkeypatch)
    only_id = cfg_mod.load_naver_search_api_config(env={cfg_mod.ENV_CLIENT_ID: "abc"})
    assert only_id.live_enabled is False
    only_secret = cfg_mod.load_naver_search_api_config(env={cfg_mod.ENV_CLIENT_SECRET: "xyz"})
    assert only_secret.live_enabled is False
    both = cfg_mod.load_naver_search_api_config(
        env={cfg_mod.ENV_CLIENT_ID: "abc", cfg_mod.ENV_CLIENT_SECRET: "xyz"}
    )
    assert both.live_enabled is True


def test_redacted_does_not_expose_secret_values():
    cfg = cfg_mod.NaverSearchApiConfig(
        client_id="my-very-secret-id",
        client_secret="my-very-secret-value",
    )
    red = cfg.redacted()
    serialized = repr(red)
    assert "my-very-secret-id" not in serialized
    assert "my-very-secret-value" not in serialized
    assert red["client_id_present"] is True
    assert red["client_secret_present"] is True
    assert red["client_id_length"] == len("my-very-secret-id")
    assert red["client_secret_length"] == len("my-very-secret-value")
    assert red["base_url"] == cfg_mod.DEFAULT_BASE_URL
    assert red["timeout_seconds"] == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_redacted_when_missing_keys_returns_zero_lengths():
    cfg = cfg_mod.NaverSearchApiConfig(client_id=None, client_secret=None)
    red = cfg.redacted()
    assert red["client_id_present"] is False
    assert red["client_secret_present"] is False
    assert red["client_id_length"] == 0
    assert red["client_secret_length"] == 0


def test_default_base_url_and_timeout():
    cfg = cfg_mod.load_naver_search_api_config(env={})
    assert cfg.base_url == cfg_mod.DEFAULT_BASE_URL
    assert cfg.timeout_seconds == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_base_url_override_strips_trailing_slash():
    cfg = cfg_mod.load_naver_search_api_config(
        env={cfg_mod.ENV_BASE_URL: "https://example.test/v1/search/"}
    )
    assert cfg.base_url == "https://example.test/v1/search"


def test_timeout_override_parsed_as_float():
    cfg = cfg_mod.load_naver_search_api_config(
        env={cfg_mod.ENV_TIMEOUT_SECONDS: "5.5"}
    )
    assert cfg.timeout_seconds == 5.5


@pytest.mark.parametrize("bad", ["", "abc", "0", "-1"])
def test_invalid_timeout_falls_back_to_default(bad):
    cfg = cfg_mod.load_naver_search_api_config(
        env={cfg_mod.ENV_TIMEOUT_SECONDS: bad}
    )
    assert cfg.timeout_seconds == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_whitespace_only_keys_treated_as_missing():
    cfg = cfg_mod.load_naver_search_api_config(
        env={cfg_mod.ENV_CLIENT_ID: "   ", cfg_mod.ENV_CLIENT_SECRET: ""}
    )
    assert cfg.client_id is None
    assert cfg.client_secret is None
    assert cfg.live_enabled is False
