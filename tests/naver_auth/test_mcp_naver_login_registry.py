"""AI 창(MCP call_api)이 네이버 자동 로그인을 부를 수 있는 허용 목록 계약 검사."""

from __future__ import annotations

import re
from pathlib import Path

# mcp 패키지 버전이 환경마다 달라 mcp_server 를 import 하지 않고 소스의 API_REGISTRY 만 읽는다.
_SRC = Path("ai_orchestrator/server/mcp_server.py").read_text(encoding="utf-8")


def _entry(key: str) -> str:
    m = re.search(rf'"{re.escape(key)}": \{{(.*?)\n    \}},', _SRC, re.S)
    assert m, f"{key} 가 API_REGISTRY 에 없다"
    return m.group(1)


def test_login_status_is_read_only_get():
    e = _entry("naver.session.status")
    assert '"method": "GET"' in e
    assert "/api/v1/naver/session/status" in e


def test_login_is_post_and_warns_against_retry():
    e = _entry("naver.login")
    assert '"method": "POST"' in e
    assert "/api/v1/naver/session/login" in e
    assert "재시도하지 말 것" in e  # 반복 실패는 계정 잠금 위험 — 설명에 항상 남아 있어야 한다


def test_no_password_field_in_registry_entries():
    for key in ("naver.session.status", "naver.login"):
        assert "password" not in _entry(key).lower()  # 비밀번호는 이 경로로 오가지 않는다
