"""Hiworks 1단계 골격 검증.

검증 항목:
- 환경변수 누락 시 require_live 에서 에러
- dry_run 기본값 (HIWORKS_DRY_RUN 미지정)
- dry_run 모드는 transport 없이도 mock 응답 반환 (네트워크 미사용)
- 모든 collector 가 동일한 CollectorResult 스키마 반환
- 응답/요청 요약에 시크릿 원문 미노출
- 비-GET 메서드 차단
"""
from __future__ import annotations

import logging

import pytest

from ai_orchestrator.connectors.hiworks import client as hiworks_client
from ai_orchestrator.connectors.hiworks import collectors as hiworks_collectors
from ai_orchestrator.connectors.hiworks import config as hiworks_config


# ── helpers ─────────────────────────────────────────────────────
def _clear_hiworks_env(monkeypatch):
    for k in (
        hiworks_config.ENV_BASE_URL,
        hiworks_config.ENV_CLIENT_ID,
        hiworks_config.ENV_CLIENT_SECRET,
        hiworks_config.ENV_OFFICE_TOKEN,
        hiworks_config.ENV_DRY_RUN,
    ):
        monkeypatch.delenv(k, raising=False)


# ── config ──────────────────────────────────────────────────────
def test_load_config_default_is_dry_run(monkeypatch):
    _clear_hiworks_env(monkeypatch)
    cfg = hiworks_config.load_config()
    assert cfg.dry_run is True
    assert cfg.has_credentials() is False
    assert cfg.base_url == hiworks_config.DEFAULT_BASE_URL


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv(hiworks_config.ENV_BASE_URL, "https://api.example.invalid")
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_ID, "cid")
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_SECRET, "csecret")
    monkeypatch.setenv(hiworks_config.ENV_OFFICE_TOKEN, "otok")
    monkeypatch.setenv(hiworks_config.ENV_DRY_RUN, "false")
    cfg = hiworks_config.load_config()
    assert cfg.base_url == "https://api.example.invalid"
    assert cfg.dry_run is False
    assert cfg.has_credentials() is True


def test_require_live_raises_with_missing_keys_only(monkeypatch):
    _clear_hiworks_env(monkeypatch)
    cfg = hiworks_config.load_config()
    with pytest.raises(hiworks_config.HiworksConfigError) as e:
        hiworks_config.require_live(cfg)
    msg = str(e.value)
    # 메시지에는 키 이름만 있어야 한다 (값 노출 금지).
    assert hiworks_config.ENV_CLIENT_ID in msg
    assert hiworks_config.ENV_OFFICE_TOKEN in msg
    # 명백한 시크릿 토큰 패턴이 들어가지 않는다.
    assert "Bearer" not in msg


def test_redacted_does_not_leak_values(monkeypatch):
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_ID, "supersecret-cid")
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_SECRET, "supersecret-cs")
    monkeypatch.setenv(hiworks_config.ENV_OFFICE_TOKEN, "supersecret-ot")
    cfg = hiworks_config.load_config()
    red = cfg.redacted()
    flat = repr(red)
    assert "supersecret-cid" not in flat
    assert "supersecret-cs" not in flat
    assert "supersecret-ot" not in flat
    # 길이 정보 형식만 노출
    assert "len=" in red["client_id"]


# ── client ──────────────────────────────────────────────────────
def test_dry_run_request_does_not_invoke_transport(monkeypatch):
    _clear_hiworks_env(monkeypatch)  # dry_run 기본 True
    called = {"n": 0}

    def transport(**_):
        called["n"] += 1
        raise AssertionError("transport must not be called in dry_run")

    client = hiworks_client.HiworksClient(transport=transport)
    resp = client.request("GET", "/v1/me")
    assert resp.status == "dry_run"
    assert called["n"] == 0
    # request_summary 에 헤더 키만 있고 토큰 원문은 없어야 한다.
    flat = repr(resp.to_dict())
    assert "Authorization" in resp.request_summary["header_keys"]
    assert "Bearer" not in flat


def test_non_get_method_blocked_in_phase_1(monkeypatch):
    _clear_hiworks_env(monkeypatch)
    client = hiworks_client.HiworksClient()
    resp = client.request("POST", "/v1/me")
    assert resp.status == "error"
    assert resp.error_code == "METHOD_NOT_ALLOWED_IN_PHASE_1"


def test_live_without_credentials_returns_unconfigured(monkeypatch):
    _clear_hiworks_env(monkeypatch)
    monkeypatch.setenv(hiworks_config.ENV_DRY_RUN, "false")  # live 시도

    def transport(**_):
        raise AssertionError("transport must not be called when unconfigured")

    client = hiworks_client.HiworksClient(transport=transport)
    resp = client.request("GET", "/v1/me")
    assert resp.status == "unconfigured"
    assert resp.error_code == "MISSING_CREDENTIALS"


def test_live_with_credentials_uses_transport(monkeypatch):
    monkeypatch.setenv(hiworks_config.ENV_BASE_URL, "https://api.example.invalid")
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_ID, "cid")
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_SECRET, "cs")
    monkeypatch.setenv(hiworks_config.ENV_OFFICE_TOKEN, "ot")
    monkeypatch.setenv(hiworks_config.ENV_DRY_RUN, "false")

    seen = {}

    def transport(method, url, headers, params, json):
        seen["method"] = method
        seen["url"] = url
        seen["header_keys"] = sorted(headers.keys())
        return 200, {"items": [{"id": "u1"}]}

    client = hiworks_client.HiworksClient(transport=transport)
    resp = client.request("GET", "/v1/me")
    assert resp.status == "ok"
    assert resp.http_status == 200
    assert seen["method"] == "GET"
    assert seen["url"] == "https://api.example.invalid/v1/me"
    assert "Authorization" in seen["header_keys"]


def test_logging_does_not_leak_secrets(monkeypatch, caplog):
    monkeypatch.setenv(hiworks_config.ENV_CLIENT_SECRET, "super-secret-value-XYZ")
    monkeypatch.setenv(hiworks_config.ENV_OFFICE_TOKEN, "super-token-ABC")
    _clear_dryrun = lambda: monkeypatch.delenv(hiworks_config.ENV_DRY_RUN, raising=False)
    _clear_dryrun()

    client = hiworks_client.HiworksClient()
    with caplog.at_level(logging.DEBUG, logger=hiworks_client.__name__):
        client.request("GET", "/v1/me")

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "super-secret-value-XYZ" not in log_text
    assert "super-token-ABC" not in log_text


# ── collectors ──────────────────────────────────────────────────
COLLECTORS = [
    ("my_profile", hiworks_collectors.collect_my_profile),
    ("org_units", hiworks_collectors.collect_org_units),
    ("org_members", hiworks_collectors.collect_org_members),
    ("attendance_summary", hiworks_collectors.collect_attendance_summary),
]


@pytest.mark.parametrize("name,fn", COLLECTORS)
def test_collectors_dry_run_schema(monkeypatch, name, fn):
    _clear_hiworks_env(monkeypatch)  # dry_run default
    result = fn()
    d = result.to_dict()
    # 스키마 일관성
    for key in ("collector", "status", "items", "item_count", "raw"):
        assert key in d, f"{name} missing key {key}"
    assert d["collector"] == name
    assert d["status"] == "dry_run"
    assert isinstance(d["items"], list)
    assert d["item_count"] == len(d["items"])
    # mock 페이로드도 가짜 시크릿/PII 패턴 미포함
    flat = repr(d)
    assert "Bearer" not in flat
    assert "@" not in flat  # mock 이메일 흉내 금지


def test_collector_unconfigured_propagates(monkeypatch):
    _clear_hiworks_env(monkeypatch)
    monkeypatch.setenv(hiworks_config.ENV_DRY_RUN, "false")
    result = hiworks_collectors.collect_my_profile()
    assert result.status == "unconfigured"
    assert result.error_code == "MISSING_CREDENTIALS"
