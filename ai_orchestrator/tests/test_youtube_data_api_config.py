"""Tests for ai_orchestrator/connectors/youtube_data_api_config.py (F-4S-3)."""
from __future__ import annotations

import pytest

from ai_orchestrator.connectors import youtube_data_api_config as cfg_mod


def _clear(monkeypatch):
    for k in (
        cfg_mod.ENV_API_KEY,
        cfg_mod.ENV_BASE_URL,
        cfg_mod.ENV_TIMEOUT_SECONDS,
    ):
        monkeypatch.delenv(k, raising=False)


def test_load_returns_unconfigured_when_no_env(monkeypatch):
    _clear(monkeypatch)
    cfg = cfg_mod.load_youtube_data_api_config(env={})
    assert cfg.api_key is None
    assert cfg.live_enabled is False


def test_live_enabled_only_when_key_present(monkeypatch):
    _clear(monkeypatch)
    no_key = cfg_mod.load_youtube_data_api_config(env={})
    assert no_key.live_enabled is False
    with_key = cfg_mod.load_youtube_data_api_config(env={cfg_mod.ENV_API_KEY: "abc"})
    assert with_key.live_enabled is True


def test_redacted_does_not_expose_key_value():
    cfg = cfg_mod.YoutubeDataApiConfig(api_key="my-very-secret-youtube-key")
    red = cfg.redacted()
    serialized = repr(red)
    assert "my-very-secret-youtube-key" not in serialized
    assert red["api_key_present"] is True
    assert red["api_key_length"] == len("my-very-secret-youtube-key")
    assert red["base_url"] == cfg_mod.DEFAULT_BASE_URL
    assert red["timeout_seconds"] == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_redacted_when_missing_key_returns_zero_length():
    cfg = cfg_mod.YoutubeDataApiConfig(api_key=None)
    red = cfg.redacted()
    assert red["api_key_present"] is False
    assert red["api_key_length"] == 0


def test_default_base_url_and_timeout():
    cfg = cfg_mod.load_youtube_data_api_config(env={})
    assert cfg.base_url == cfg_mod.DEFAULT_BASE_URL
    assert cfg.timeout_seconds == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_base_url_override_strips_trailing_slash():
    cfg = cfg_mod.load_youtube_data_api_config(
        env={cfg_mod.ENV_BASE_URL: "https://example.test/youtube/v3/"}
    )
    assert cfg.base_url == "https://example.test/youtube/v3"


def test_timeout_override_parsed_as_float():
    cfg = cfg_mod.load_youtube_data_api_config(
        env={cfg_mod.ENV_TIMEOUT_SECONDS: "5.5"}
    )
    assert cfg.timeout_seconds == 5.5


@pytest.mark.parametrize("bad", ["", "abc", "0", "-1"])
def test_invalid_timeout_falls_back_to_default(bad):
    cfg = cfg_mod.load_youtube_data_api_config(
        env={cfg_mod.ENV_TIMEOUT_SECONDS: bad}
    )
    assert cfg.timeout_seconds == cfg_mod.DEFAULT_TIMEOUT_SECONDS


def test_whitespace_only_key_treated_as_missing():
    cfg = cfg_mod.load_youtube_data_api_config(
        env={cfg_mod.ENV_API_KEY: "   "}
    )
    assert cfg.api_key is None
    assert cfg.live_enabled is False
