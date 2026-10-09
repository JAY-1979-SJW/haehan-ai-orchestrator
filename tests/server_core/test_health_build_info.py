"""/api/v1/health 의 git_sha·build_time(운영 배포 가시성, R3) — 주입·기본값·형식 검증과 배포 파일 정합."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_orchestrator.asgi import app

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app, raise_server_exceptions=True)

SHA = "db235656a1b2c3d4e5f60718293a4b5c6d7e8f90"


def _health() -> dict:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    return r.json()


def test_health_defaults_to_unknown_without_build_env(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_TIME", raising=False)
    body = _health()
    assert body["git_sha"] == "unknown"
    assert body["build_time"] == "unknown"


def test_health_reports_injected_build_values(monkeypatch):
    monkeypatch.setenv("GIT_SHA", SHA)
    monkeypatch.setenv("BUILD_TIME", "2026-10-07T12:34:56Z")
    body = _health()
    assert body["git_sha"] == SHA
    assert body["build_time"] == "2026-10-07T12:34:56Z"


def test_health_keeps_existing_keys(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    body = _health()
    assert body["status"] == "ok"
    assert body["service"] == "haehan-ai-orchestrator"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "not-a-sha",
        "db2356",
        "db235656;rm -rf /",
        "g" * 40,
        "a" * 41,
        "<script>",
    ],
)
def test_health_rejects_malformed_git_sha(monkeypatch, bad):
    # 7자 미만·비16진·길이 초과·특수문자는 그대로 노출하지 않고 "unknown"
    monkeypatch.setenv("GIT_SHA", bad)
    assert _health()["git_sha"] == "unknown"


def test_health_accepts_short_sha(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "db23565")
    assert _health()["git_sha"] == "db23565"


def test_health_rejects_malformed_build_time(monkeypatch):
    monkeypatch.setenv("BUILD_TIME", "x" * 41)
    assert _health()["build_time"] == "unknown"
    monkeypatch.setenv("BUILD_TIME", "<b>now</b>")
    assert _health()["build_time"] == "unknown"


def test_dockerfile_injects_build_args_into_env():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG GIT_SHA=unknown" in text
    assert "ARG BUILD_TIME=unknown" in text
    assert "GIT_SHA=${GIT_SHA}" in text
    assert "BUILD_TIME=${BUILD_TIME}" in text
    # 헬스체크는 그대로 /api/v1/health 200 만 본다(값이 unknown 이어도 컨테이너가 unhealthy 가 되지 않는다)
    assert "http://127.0.0.1:8400/api/v1/health" in text


def test_compose_passes_build_args_with_unknown_default():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "GIT_SHA: ${GIT_SHA:-unknown}" in text
    assert "BUILD_TIME: ${BUILD_TIME:-unknown}" in text
    assert "http://127.0.0.1:8400/api/v1/health" in text


def test_server_deploy_passes_sha_to_compose_build():
    text = (ROOT / "tools" / "server_deploy.py").read_text(encoding="utf-8")
    assert '"rev-parse", "HEAD"' in text
    assert 'env["GIT_SHA"]' in text
    assert "env=_build_env()" in text
