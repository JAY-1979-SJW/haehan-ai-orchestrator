"""JWT_SECRET 시작 점검(asgi._check_jwt_secret) — 없으면 경고, JWT_SECRET_REQUIRED 면 시작 중단. (초안)"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_orchestrator import asgi
from ai_orchestrator.core import config

ROOT = Path(__file__).resolve().parents[2]


def _set(monkeypatch, *, auth=True, configured=True, required=False, secret="s" * 40):
    monkeypatch.setattr(config, "AUTH_ENABLED", auth)
    monkeypatch.setattr(config, "JWT_SECRET_CONFIGURED", configured)
    monkeypatch.setattr(config, "JWT_SECRET_REQUIRED", required)
    monkeypatch.setattr(config, "JWT_SECRET", secret)


def test_missing_secret_logs_error_by_default(monkeypatch, caplog):
    _set(monkeypatch, configured=False)
    with caplog.at_level(logging.ERROR, logger=asgi.logger.name):
        asgi._check_jwt_secret()  # 시작을 막지 않는다
    assert "JWT_SECRET 이 설정되지 않았습니다" in caplog.text


def test_missing_secret_blocks_startup_when_required(monkeypatch):
    _set(monkeypatch, configured=False, required=True)
    with pytest.raises(RuntimeError, match="JWT_SECRET_REQUIRED"):
        asgi._check_jwt_secret()


def test_auth_disabled_skips_check_even_when_required(monkeypatch, caplog):
    _set(monkeypatch, auth=False, configured=False, required=True)
    asgi._check_jwt_secret()
    assert caplog.text == ""


def test_configured_long_secret_is_silent(monkeypatch, caplog):
    _set(monkeypatch, required=True)
    with caplog.at_level(logging.WARNING, logger=asgi.logger.name):
        asgi._check_jwt_secret()
    assert "JWT_SECRET" not in caplog.text


def test_short_secret_logs_error_but_does_not_block(monkeypatch, caplog):
    _set(monkeypatch, required=True, secret="short")
    with caplog.at_level(logging.ERROR, logger=asgi.logger.name):
        asgi._check_jwt_secret()
    assert "너무 짧습니다" in caplog.text


def test_secret_value_is_never_logged(monkeypatch, caplog):
    _set(monkeypatch, secret="short-but-secret")
    with caplog.at_level(logging.DEBUG, logger=asgi.logger.name):
        asgi._check_jwt_secret()
    assert "short-but-secret" not in caplog.text


def test_lifespan_runs_the_check():
    assert "_check_jwt_secret()" in (ROOT / "ai_orchestrator" / "asgi.py").read_text(encoding="utf-8")


def test_compose_and_env_example_document_the_setting():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "JWT_SECRET_REQUIRED: ${JWT_SECRET_REQUIRED:-false}" in compose  # 기본은 경고만(운영 즉시 중단 방지)
    assert "JWT_SECRET: ${JWT_SECRET:-}" in compose  # admin-web 미들웨어에도 전달
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "\nJWT_SECRET=\n" in example
    assert "JWT_SECRET_REQUIRED=false" in example
