"""Playwright 로컬 smoke 테스트

안전한 URL(about:blank, data URL, 로컬 HTML fixture)만 사용한다.
외부 인증 사이트에 접속하지 않는다.
Playwright 미설치 환경에서는 skip한다.
"""

from __future__ import annotations

import pathlib

import pytest

_FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "local_agent_safe_smoke_page.html"


def _fixture_url() -> str:
    return _FIXTURE_PATH.as_uri()


@pytest.fixture(scope="module")
def playwright_ready():
    pytest.importorskip("playwright")
    from core.agent_runtime.runtime.playwright.playwright_bootstrap import (
        PLAYWRIGHT_READY,
        check_playwright_status,
    )

    result = check_playwright_status()
    if result["status"] != PLAYWRIGHT_READY:
        pytest.skip(f"Playwright 준비 안 됨: {result['message_ko']}")


@pytest.fixture(scope="module")
def fixture_exists():
    if not _FIXTURE_PATH.exists():
        pytest.skip(f"fixture 파일 없음: {_FIXTURE_PATH}")


# ── 1. about:blank smoke ──────────────────────────────────────────────────────


def test_open_about_blank(playwright_ready):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("open_url", "about:blank", domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    assert result["status"] == STATUS_COMPLETED


def test_read_data_url(playwright_ready):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("read_page", "data:text/html,<h1>smoke</h1>", domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    assert result["status"] == STATUS_COMPLETED


# ── 2. fixture open_url / read_page ──────────────────────────────────────────


def test_open_fixture_url(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("open_url", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    assert result["status"] == STATUS_COMPLETED


def test_read_fixture_page(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("read_page", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    assert "body_text_sample" in result.get("extracted_data", {})


def test_read_fixture_title_hint(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("read_page", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result.get("title_hint")


# ── 3. extract_text ───────────────────────────────────────────────────────────


def test_extract_h1_text(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("extract_text", _fixture_url(), domain="smoke")
    task.setdefault("metadata", {})["selector"] = "h1"
    result = run_task(task)
    assert result["ok"] is True
    assert result["status"] == STATUS_COMPLETED
    assert "smoke" in result.get("extracted_data", {}).get("text", "").lower()


def test_extract_smoke_marker(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("extract_text", _fixture_url(), domain="smoke")
    task.setdefault("metadata", {})["selector"] = "#smoke-marker"
    result = run_task(task)
    assert "SMOKE_OK" in result.get("extracted_data", {}).get("text", "")


# ── 4. extract_table ──────────────────────────────────────────────────────────


def test_extract_table_rows(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("extract_table", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    rows = result.get("extracted_data", {}).get("table_rows", [])
    assert len(rows) >= 3


def test_extract_table_has_header_row(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("extract_table", _fixture_url(), domain="smoke")
    result = run_task(task)
    rows = result.get("extracted_data", {}).get("table_rows", [])
    header = rows[0] if rows else []
    assert "번호" in header or "항목" in header


# ── 5. capture_screenshot ─────────────────────────────────────────────────────


def test_capture_screenshot(playwright_ready, fixture_exists):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("capture_screenshot", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    assert result["status"] == STATUS_COMPLETED


def test_capture_screenshot_filename_only(playwright_ready, fixture_exists):
    """스크린샷은 파일명만 반환하고 이미지 바이너리는 포함하지 않는다."""
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("capture_screenshot", _fixture_url(), domain="smoke")
    result = run_task(task)
    filename = result.get("extracted_data", {}).get("screenshot_filename", "")
    assert filename.endswith(".png")
    assert "bytes" not in result
    assert "binary" not in result


# ── 6. detect_login_status ────────────────────────────────────────────────────


def test_detect_login_status_no_signal(playwright_ready, fixture_exists):
    """smoke 페이지에서 인증 신호 없음 (hidden 섹션)."""
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_COMPLETED,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("detect_login_status", _fixture_url(), domain="smoke")
    result = run_task(task)
    assert result["ok"] is True
    # hidden 섹션이므로 신호 없음 → COMPLETED
    assert result["status"] == STATUS_COMPLETED


def test_detect_login_status_result_no_sensitive(playwright_ready, fixture_exists):
    """detect_login_status 결과에 민감값이 없어야 한다."""
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("detect_login_status", _fixture_url(), domain="smoke")
    result = run_task(task)
    for field in ("cookie", "session", "password", "otp", "token"):
        assert field not in result


# ── 7. wait_for_user_auth ─────────────────────────────────────────────────────


def test_wait_for_user_auth_returns_waiting(playwright_ready):
    from ai_orchestrator.contracts.local_task_protocol import (
        STATUS_WAITING_USER_AUTH,
        build_task,
    )
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("wait_for_user_auth", "", domain="smoke")
    result = run_task(task)
    assert result["status"] == STATUS_WAITING_USER_AUTH


def test_wait_for_user_auth_no_browser_access(playwright_ready):
    """wait_for_user_auth는 브라우저를 열지 않는다 (url 비어도 오류 없음)."""
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("wait_for_user_auth", "", domain="smoke")
    result = run_task(task)
    assert result["ok"] is False  # auth 대기이므로 ok=False
    assert "인증" in result.get("message_ko", "") or "비밀번호" in result.get("message_ko", "")


# ── 8. 결과 안전성 공통 검증 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "action,url",
    [
        ("open_url", "about:blank"),
        ("read_page", "data:text/html,<p>safe</p>"),
    ],
)
def test_result_no_sensitive_fields(playwright_ready, action, url):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task(action, url, domain="smoke")
    result = run_task(task)
    for field in ("cookie", "session", "password", "otp", "token", "npki"):
        assert field not in result


def test_result_fixed_safe_fields_false(playwright_ready):
    from ai_orchestrator.contracts.local_task_protocol import build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("open_url", "about:blank", domain="smoke")
    result = run_task(task)
    assert result.get("sensitive_data_collected") is False
    assert result.get("cookie_exported") is False
    assert result.get("session_exported") is False
    assert result.get("password_collected") is False
    assert result.get("otp_collected") is False
    assert result.get("certificate_password_collected") is False


# ── 9. 지원하지 않는 action 차단 ────────────────────────────────────────────────


def test_unsupported_action_blocked(playwright_ready):
    from ai_orchestrator.contracts.local_task_protocol import STATUS_BLOCKED, build_task
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    task = build_task("open_url", "about:blank")
    task["action"] = "auto_bid_submit"
    result = run_task(task)
    assert result["status"] == STATUS_BLOCKED
