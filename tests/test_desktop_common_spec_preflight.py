"""tests/test_desktop_common_spec_preflight.py
P4 공통 스펙 테스트 — /local-agent/preflight / exception handler / provider error.

범위:
  P1: /local-agent/preflight schema (1~9)
  P2: exception handler status code 보존 + 500 마스킹 (10~12)
  P3: provider 오류 응답 shape + 기존 키 보존 (13~14)
  공통: secret scan / 외부 AI 호출 없음 (15~16)

원칙:
  - 실제 Anthropic/Claude CLI 호출 없음 (monkeypatch)
  - 실제 API key 불필요
  - CDP 실제 실행 없음
  - 서버 배포 없음
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_modules():
    """각 테스트 전 desktop 모듈 캐시 초기화."""
    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]
    yield
    for mn in list(sys.modules.keys()):
        if mn.startswith("desktop"):
            del sys.modules[mn]


@pytest.fixture()
def local_server():
    from desktop import local_server as ls

    ls._remote_enabled = lambda: True
    ls._verify_token = lambda t: True
    return ls


@pytest.fixture()
def svc():
    from desktop import local_agent_service as s

    return s


@pytest.fixture()
def client(local_server):
    from fastapi.testclient import TestClient

    return TestClient(local_server.app, raise_server_exceptions=False)


@pytest.fixture()
def no_provider(svc, monkeypatch):
    """API key 없음 + CLI 없음 환경."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(svc.shutil, "which", lambda n: None)
    monkeypatch.setattr(svc, "_anthropic_available", lambda: False)
    yield


@pytest.fixture()
def mock_provider(svc, monkeypatch):
    """mock API key + SDK available 환경 (외부 호출 없음)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mock-test-key")
    monkeypatch.setattr(svc, "_anthropic_available", lambda: True)
    monkeypatch.setattr(svc.shutil, "which", lambda n: "/usr/bin/claude")
    yield


@pytest.fixture()
def cdp_down(svc, monkeypatch, mock_provider):
    """CDP down + provider 정상 환경."""
    monkeypatch.setattr(svc, "_check_cdp_available", lambda: False)
    yield


REQUIRED_SCHEMA_FIELDS = [
    "schema_version",
    "ok",
    "can_run",
    "blocking_reasons",
    "user_message",
    "next_actions",
    "provider_status",
    "api_key_set",
    "claude_cli_available",
    "health",
    "whoami",
    "consent",
    "optional_status",
    "warnings",
]

EXISTING_RUN_KEYS = {"ok", "result", "provider", "model", "tool_calls"}

FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "raw_api_key",
    "token",
    "bearer",
    "cookie",
    "session",
    "authorization",
    "database_url",
    "password",
    "secret",
}

SK_PATTERN = re.compile(r"sk-[a-z0-9\-_]{6,}", re.IGNORECASE)


def _assert_no_secret(body: str, label: str = "") -> None:
    b = body.lower()
    for k in FORBIDDEN_KEYS:
        if k == "api_key":
            # api_key_set 오탐 방지
            assert f'"{k}"' not in b or '"api_key_set"' in b, f"[{label}] 금지 필드 '{k}' 응답 노출"
        else:
            assert f'"{k}"' not in b, f"[{label}] 금지 필드 '{k}' 응답 노출"
    assert not SK_PATTERN.search(b), f"[{label}] sk- raw key 응답 노출"


# ══════════════════════════════════════════════════════════════════════════════
# P1 — /local-agent/preflight schema
# ══════════════════════════════════════════════════════════════════════════════


class TestPreflightSchema:
    """테스트 1~3: 스키마 구조 및 기본 필드"""

    def test_01_full_schema_fields_present(self, client, no_provider):
        """1. /local-agent/preflight 응답에 필수 13개 top-level 필드 전부 존재."""
        r = client.get("/local-agent/preflight")
        assert r.status_code == 200
        data = r.json()
        for field in REQUIRED_SCHEMA_FIELDS:
            assert field in data, f"필수 필드 누락: {field}"

    def test_02_schema_version_fixed(self, client, no_provider):
        """2. schema_version = 'local_agent_preflight_v1' 고정값."""
        data = client.get("/local-agent/preflight").json()
        assert data["schema_version"] == "local_agent_preflight_v1"

    def test_03_field_name_provider_status_not_providers(self, client, no_provider):
        """3. 'provider_status' 필드명 사용 — 구 'providers' 금지."""
        data = client.get("/local-agent/preflight").json()
        assert "provider_status" in data
        assert "providers" not in data


class TestPreflightCanRun:
    """테스트 4~5: can_run 계산"""

    def test_04_no_provider_can_run_false(self, client, no_provider):
        """4. provider 없음 → can_run=false."""
        data = client.get("/local-agent/preflight").json()
        assert data["can_run"] is False

    def test_05_mock_provider_can_run_true(self, client, mock_provider):
        """5. mock provider 준비 → can_run=true."""
        data = client.get("/local-agent/preflight").json()
        assert data["can_run"] is True


class TestPreflightApiKeySet:
    """테스트 6~7: api_key_set / claude_cli_available boolean"""

    def test_06_api_key_set_is_boolean(self, client, no_provider):
        """6. api_key_set top-level 과 nested 모두 boolean."""
        data = client.get("/local-agent/preflight").json()
        top = data.get("api_key_set")
        assert isinstance(top, bool), f"top-level api_key_set 타입: {type(top)}"
        nested = data["provider_status"]["anthropic_sdk"]["api_key_set"]
        assert isinstance(nested, bool), f"nested api_key_set 타입: {type(nested)}"

    def test_07_claude_cli_available_is_boolean(self, client, no_provider):
        """7. claude_cli_available top-level boolean."""
        data = client.get("/local-agent/preflight").json()
        val = data.get("claude_cli_available")
        assert isinstance(val, bool), f"claude_cli_available 타입: {type(val)}"


class TestPreflightFieldNames:
    """테스트 8: 필드명 고정"""

    def test_08_optional_status_not_optional(self, client, no_provider):
        """8. 'optional_status' 필드명 사용 — 구 'optional' 금지."""
        data = client.get("/local-agent/preflight").json()
        assert "optional_status" in data
        assert "optional" not in data


class TestPreflightOptionalNotBlocking:
    """테스트 9: CDP down 이어도 core can_run 차단 금지"""

    def test_09_cdp_down_does_not_block_can_run(self, client, cdp_down):
        """9. CDP down → optional_status false, can_run=true, warnings 에만 경고."""
        data = client.get("/local-agent/preflight").json()
        assert data["optional_status"]["cdp"]["available"] is False
        assert data["can_run"] is True
        warnings = data.get("warnings", [])
        assert "CDP_BROWSER_NOT_RUNNING" in warnings


# ══════════════════════════════════════════════════════════════════════════════
# P2 — exception handler status code 보존 + 500 마스킹
# ══════════════════════════════════════════════════════════════════════════════


class TestExceptionHandlerP2:
    """테스트 10~12: exception handler 동작 — 핸들러 함수 직접 호출."""

    def _mock_req(self):
        req = MagicMock()
        req.method = "GET"
        req.url.path = "/test"
        return req

    def test_10_http_exception_status_preserved(self, local_server):
        """10. HTTPException 404/403/401 status_code 보존."""
        from fastapi import HTTPException

        req = self._mock_req()
        for code in (404, 403, 401):
            r = asyncio.run(local_server._http_exception_handler(req, HTTPException(status_code=code)))
            assert r.status_code == code, f"HTTPException {code} → status={r.status_code}"
            body = json.loads(r.body)
            assert "detail" in body

    def test_11_validation_error_422_preserved(self, local_server):
        """11. RequestValidationError → 422 보존."""
        from fastapi.exceptions import RequestValidationError

        req = self._mock_req()
        rve = RequestValidationError([{"loc": ("body",), "msg": "field required", "type": "missing"}])
        r = asyncio.run(local_server._validation_exception_handler(req, rve))
        assert r.status_code == 422
        body = json.loads(r.body)
        assert "detail" in body

    def test_12_unexpected_exception_500_masked(self, local_server):
        """12. 예상 밖 RuntimeError → 500 마스킹, stack trace / raw msg 미노출."""
        req = self._mock_req()
        exc = RuntimeError("internal secret: sk-real-key-xyz123")
        r = asyncio.run(local_server._generic_exception_handler(req, exc))
        assert r.status_code == 500
        body_str = r.body.decode()
        assert "sk-real-key-xyz123" not in body_str, "raw exception msg 노출"
        assert "RuntimeError" not in body_str, "exception type 노출"
        assert "Traceback" not in body_str, "traceback 노출"
        body = json.loads(body_str)
        assert "detail" in body


# ══════════════════════════════════════════════════════════════════════════════
# P3 — provider 오류 응답 shape + 기존 키 보존
# ══════════════════════════════════════════════════════════════════════════════


class TestProviderErrorResponseP3:
    """테스트 13~14: run_local_agent 오류 응답 shape."""

    def test_13_provider_error_response_shape(self, svc, monkeypatch):
        """13. NO_PROVIDER_AVAILABLE 응답에 기존 키 + P3 추가 키 모두 존재."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(svc.shutil, "which", lambda n: None)
        monkeypatch.setattr(svc, "_anthropic_available", lambda: False)

        data = asyncio.run(svc.run_local_agent({"prompt": "test"}))

        # 기존 키
        for k in EXISTING_RUN_KEYS:
            assert k in data, f"기존 키 누락: {k}"
        # P3 추가 키
        for k in ("error_code", "user_message", "next_actions", "provider_status", "can_retry", "safe_to_show"):
            assert k in data, f"추가 키 누락: {k}"

        assert data["ok"] is False
        assert data["error_code"] == "NO_PROVIDER_AVAILABLE"
        assert data["safe_to_show"] is True
        assert isinstance(data["provider_status"].get("anthropic_sdk", {}).get("api_key_set"), bool)

    def test_14_existing_run_keys_preserved_on_success(self, svc, monkeypatch):
        """14. 정상 실행 경로에서 기존 5개 키 보존."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mock")
        monkeypatch.setattr(svc, "_anthropic_available", lambda: True)
        monkeypatch.setattr(svc.shutil, "which", lambda n: "/usr/bin/claude")

        async def _mock_no_mcp(prompt, model):
            return "mock result"

        monkeypatch.setattr(svc, "_run_with_anthropic_no_mcp", _mock_no_mcp)

        data = asyncio.run(svc.run_local_agent({"prompt": "test", "use_mcp": False}))

        for k in EXISTING_RUN_KEYS:
            assert k in data, f"성공 응답에 기존 키 누락: {k}"
        assert data["ok"] is True
        assert data["provider"] == "anthropic_sdk"


# ══════════════════════════════════════════════════════════════════════════════
# 공통 — secret scan / 외부 AI 호출 없음
# ══════════════════════════════════════════════════════════════════════════════


class TestSecretScanAndNoExternalCall:
    """테스트 15~16: secret 미노출 + 외부 AI 호출 없음."""

    def test_15_no_secret_in_preflight_response(self, client, no_provider):
        """15. /local-agent/preflight 응답에 secret/token/raw key 미노출."""
        r = client.get("/local-agent/preflight")
        _assert_no_secret(r.text, "preflight no_provider")

    def test_15b_no_secret_in_mock_provider_response(self, client, mock_provider):
        """15b. mock provider 응답에도 raw API key 미노출."""
        r = client.get("/local-agent/preflight")
        body = r.text
        assert "sk-mock-test-key" not in body, "mock API key 원문 노출"
        _assert_no_secret(body, "preflight mock_provider")

    def test_15c_no_secret_in_run_error_response(self, svc, monkeypatch):
        """15c. provider 오류 응답에 raw key / DB URL 미노출."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(svc.shutil, "which", lambda n: None)
        monkeypatch.setattr(svc, "_anthropic_available", lambda: False)

        data = asyncio.run(svc.run_local_agent({"prompt": "test"}))
        body = json.dumps(data)
        _assert_no_secret(body, "run error response")

    def test_15d_execution_failed_no_raw_exception(self, svc, monkeypatch):
        """15d. EXECUTION_FAILED 응답에 raw exception 원문 / DB 자격증명 미노출."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mock-exec-test")
        monkeypatch.setattr(svc, "_anthropic_available", lambda: True)
        monkeypatch.setattr(svc.shutil, "which", lambda n: "/usr/bin/claude")

        async def _crash(prompt, model):
            raise ValueError("postgresql://admin:sk-db-secret@db.internal/prod")

        monkeypatch.setattr(svc, "_run_with_anthropic_no_mcp", _crash)

        data = asyncio.run(svc.run_local_agent({"prompt": "test", "use_mcp": False}))
        body = json.dumps(data)
        assert "postgresql://" not in body, "DB URL 노출"
        assert "sk-db-secret" not in body, "DB secret 노출"
        assert "db.internal" not in body, "internal host 노출"
        _assert_no_secret(body, "execution_failed")

    def test_16_no_external_ai_call_on_no_provider(self, svc, monkeypatch):
        """16. provider 없음 상태에서 외부 AI 호출 없음.
        _run_with_anthropic_no_mcp / _run_with_claude_code_cli 가 호출되면 FAIL.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(svc.shutil, "which", lambda n: None)
        monkeypatch.setattr(svc, "_anthropic_available", lambda: False)

        called = []

        async def _should_not_call(*a, **kw):
            called.append("anthropic")
            raise AssertionError("외부 Anthropic API 호출됨")

        async def _should_not_call_cli(prompt):
            called.append("cli")
            raise AssertionError("외부 claude CLI 호출됨")

        monkeypatch.setattr(svc, "_run_with_anthropic_no_mcp", _should_not_call)
        monkeypatch.setattr(svc, "_run_with_claude_code_cli", _should_not_call_cli)

        data = asyncio.run(svc.run_local_agent({"prompt": "test"}))
        assert not called, f"외부 AI 호출 발생: {called}"
        assert data["ok"] is False
        assert data["error_code"] == "NO_PROVIDER_AVAILABLE"
