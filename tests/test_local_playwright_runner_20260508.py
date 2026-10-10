"""로컬 Playwright runner shape 테스트 (실제 브라우저 미실행)"""

from __future__ import annotations

import pytest

from ai_orchestrator.contracts.local_task_protocol import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_WAITING_USER_AUTH,
    build_task,
    validate_result,
)
from core.agent_runtime.runtime.playwright.playwright_runner import run_task

# ── Playwright 미설치 환경에서는 STATUS_FAILED 반환 ───────────────────────────


def _is_playwright_available() -> bool:
    try:
        import playwright  # noqa

        return True
    except ImportError:
        return False


def test_run_open_url_no_playwright():
    """Playwright 미설치 시 FAILED 반환 (shape 검증)."""
    if _is_playwright_available():
        pytest.skip("Playwright 설치됨 - 실제 브라우저 테스트는 별도 smoke로 수행")
    t = build_task("open_url", "https://www.g2b.go.kr/notice")
    r = run_task(t)
    assert r["status"] == STATUS_FAILED
    assert r["ok"] is False
    assert "playwright" in r["message_ko"].lower() or "미설치" in r["message_ko"]


def test_run_result_schema_valid():
    """run_task 결과가 항상 유효한 schema를 반환하는지 확인."""
    if _is_playwright_available():
        pytest.skip("실제 실행 환경 - smoke test로 수행")
    t = build_task("read_page", "https://www.g2b.go.kr")
    r = run_task(t)
    violations = validate_result(r)
    assert violations == [], f"schema 위반: {violations}"


def test_run_result_no_sensitive_fields():
    """run_task 결과에 민감 필드 없음."""
    if _is_playwright_available():
        pytest.skip("실제 실행 환경 - smoke test로 수행")
    t = build_task("open_url", "https://www.g2b.go.kr")
    r = run_task(t)
    for field in ("cookie", "session", "password", "otp", "token"):
        assert field not in r or r.get(field) in (None, False, "", [], {})


def test_run_blocked_action():
    """지원하지 않는 action → BLOCKED."""
    t = build_task("open_url", "https://www.g2b.go.kr")
    t["action"] = "unknown_action"
    r = run_task(t)
    assert r["status"] in (STATUS_BLOCKED, STATUS_FAILED)


# ── wait_for_user_auth shape 검증 ─────────────────────────────────────────────


def test_wait_for_user_auth_shape():
    """wait_for_user_auth는 항상 WAITING_USER_AUTH 반환 (Playwright 불필요)."""
    # wait_for_user_auth는 브라우저 실행 없이 바로 반환
    from core.agent_runtime.runtime.playwright.playwright_runner import _run_wait_for_user_auth

    t = build_task("wait_for_user_auth", "https://www.g2b.go.kr/login")
    r = _run_wait_for_user_auth(None, t)
    assert r["status"] == STATUS_WAITING_USER_AUTH
    assert "사용자 PC" in r["message_ko"]
    assert r["cookie_exported"] is False
    assert r["password_collected"] is False


def test_wait_for_user_auth_no_credentials():
    from core.agent_runtime.runtime.playwright.playwright_runner import _run_wait_for_user_auth

    t = build_task("wait_for_user_auth", "https://www.g2b.go.kr/login")
    r = _run_wait_for_user_auth(None, t)
    assert r.get("otp_collected") is False
    assert r.get("certificate_password_collected") is False
