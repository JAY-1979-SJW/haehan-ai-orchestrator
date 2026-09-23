"""External URL Blocker — 서버 측 외부 URL 실행 강제 차단."""

from __future__ import annotations

from typing import Any

from ai_orchestrator.server.execution_location_guard import (
    BLOCKED_SERVER_BROWSER_LAUNCH,
    BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
    BLOCKED_SERVER_PLAYWRIGHT_EXECUTION,
    LOCAL_AGENT_REQUIRED,
)
from ai_orchestrator.server.server_egress_policy import (
    is_external_url,
    sanitize_blocked_url_for_log,
)

_SAFE_FIELDS = (
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
)

_DEFAULT_MESSAGE_KO = "외부 웹사이트 작업은 사용자 PC 로컬 에이전트에서 실행해야 합니다."

# 차단 대상 Playwright/Selenium 모듈 이름
_BLOCKED_PLAYWRIGHT_MODULES = frozenset(
    (
        "playwright",
        "playwright.sync_api",
        "playwright.async_api",
        "playwright.sync",
        "playwright.async",
        "selenium",
        "selenium.webdriver",
        "pyppeteer",
    )
)

# 차단 대상 호출 이름
_BLOCKED_BROWSER_CALLS = frozenset(
    (
        "sync_playwright",
        "async_playwright",
        "chromium.launch",
        "firefox.launch",
        "webkit.launch",
        "Chrome",
        "Firefox",
        "WebKit",
        "webdriver.Chrome",
        "webdriver.Firefox",
    )
)


def block_external_fetch_from_server(url: str, purpose: str = "") -> dict[str, Any]:
    """서버에서 외부 URL fetch 시도 시 safe blocked 결과 반환."""
    if not is_external_url(url):
        return {
            "ok": True,
            "status": "OK",
            "execution_location": "SERVER_INTERNAL_ONLY",
            "url_safe": sanitize_blocked_url_for_log(url),
            "blocked": False,
            **{f: False for f in _SAFE_FIELDS},
        }

    return {
        "ok": False,
        "status": "BLOCKED",
        "blocked_reason": BLOCKED_SERVER_EXTERNAL_WEB_EXECUTION,
        "execution_location": LOCAL_AGENT_REQUIRED,
        "purpose": purpose,
        "url_safe": sanitize_blocked_url_for_log(url),
        "message_ko": _DEFAULT_MESSAGE_KO,
        "blocked": True,
        **{f: False for f in _SAFE_FIELDS},
    }


def guard_server_browser_action(action: str, target_url: str) -> dict[str, Any]:
    """서버에서 browser action(open_url, screenshot 등)을 외부 URL에 대해 시도하면 차단."""
    if is_external_url(target_url):
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocked_reason": BLOCKED_SERVER_BROWSER_LAUNCH,
            "execution_location": LOCAL_AGENT_REQUIRED,
            "action": action,
            "url_safe": sanitize_blocked_url_for_log(target_url),
            "message_ko": _DEFAULT_MESSAGE_KO,
            "blocked": True,
            **{f: False for f in _SAFE_FIELDS},
        }
    return {
        "ok": True,
        "status": "OK",
        "execution_location": "SERVER_INTERNAL_ONLY",
        "action": action,
        "blocked": False,
        **{f: False for f in _SAFE_FIELDS},
    }


def guard_server_playwright_invocation(module_name: str, call_name: str) -> dict[str, Any]:
    """
    서버 코드에서 Playwright/Selenium 호출을 감지하면 차단.
    (런타임 import hook 또는 정적 분석에서 사용)
    """
    if module_name in _BLOCKED_PLAYWRIGHT_MODULES or call_name in _BLOCKED_BROWSER_CALLS:
        return {
            "ok": False,
            "status": "BLOCKED",
            "blocked_reason": BLOCKED_SERVER_PLAYWRIGHT_EXECUTION,
            "execution_location": LOCAL_AGENT_REQUIRED,
            "module": module_name,
            "call": call_name,
            "message_ko": (
                f"서버에서 {module_name}.{call_name} 호출이 차단되었습니다. "
                "외부 웹 자동화는 local agent에서만 실행하세요."
            ),
            "blocked": True,
            **{f: False for f in _SAFE_FIELDS},
        }
    return {"ok": True, "blocked": False, **{f: False for f in _SAFE_FIELDS}}


def is_browser_module_call_blocked(module_name: str, call_name: str = "") -> bool:
    """주어진 모듈/호출이 서버에서 차단 대상인지 확인."""
    if module_name in _BLOCKED_PLAYWRIGHT_MODULES:
        return True
    if call_name and call_name in _BLOCKED_BROWSER_CALLS:
        return True
    return False
