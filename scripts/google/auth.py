"""Google user-present login session support.

Google credential replay is intentionally not implemented here. The supported
runtime path is:
1. Reuse an already logged-in Google/Gmail/YouTube browser session.
2. Otherwise open Google Home and let the user enter the sign-in flow.
3. Wait for the user to complete login manually.

This module must not collect, save, type, replay, or log Google passwords,
cookies, storage state, session values, or raw tokens.
"""

from __future__ import annotations

import time
from typing import Any

from core.agent_runtime.policy import site_entry_policy
from scripts.auth.login_detector import detect_login_state, wait_for_login_generic
from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)

GOOGLE_LOGIN_URL = "https://www.google.com/"
GOOGLE_SESSION_METHOD = "user_present_session"


def _mask_account(value: str | None) -> str:
    if not value:
        return ""
    text = str(value)
    if "@" not in text:
        return text[:2] + "***" if len(text) > 2 else "***"
    local, domain = text.split("@", 1)
    return f"{local[:2]}***@{domain}"


def _is_google_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(
        marker in lower
        for marker in (
            "google.",
            "gmail.",
            "mail.google.",
            "youtube.",
            "youtu.be",
        )
    )


def _is_current_google_session(page) -> dict[str, Any] | None:
    try:
        state = detect_login_state(page)
    except Exception:  # noqa: BLE001 - 구글 로그인 상태 읽기전용 확인/이동 — 감지 실패 시 None 반환하거나 페이지 복귀 실패를 무시, 로그인 세션을 파기·변경하지 않음
        return None

    current_url = str(getattr(page, "url", "") or "")
    if state.get("logged_in") and _is_google_url(current_url):
        return {
            "ok": True,
            "user": state.get("user") or "",
            "reason": "already_logged_in",
            "method": GOOGLE_SESSION_METHOD,
        }
    return None


def login_google(
    page,
    wait_for_user_s: int = 300,
) -> dict[str, Any]:
    """Ensure Google login through a user-present browser session.

    No Google ID/password arguments are accepted. The user must complete the
    login in the opened browser window.
    """
    existing = _is_current_google_session(page)
    if existing is not None:
        return existing

    _log.info("[google-auth] opening Google Home for user-present login")
    site_entry_policy.assert_main_page_first(GOOGLE_LOGIN_URL, site_key="google")
    try:
        page.goto(GOOGLE_LOGIN_URL, timeout=15000, wait_until="domcontentloaded")
    except Exception as e:  # noqa: BLE001 - 구글 로그인 상태 읽기전용 확인/이동 — 감지 실패 시 None 반환하거나 페이지 복귀 실패를 무시, 로그인 세션을 파기·변경하지 않음
        return {
            "ok": False,
            "reason": "login_page_open_failed",
            "method": GOOGLE_SESSION_METHOD,
            "error": str(e)[:120],
        }

    state = wait_for_login_generic(page, max_wait_s=wait_for_user_s, poll_interval=3.0)
    if state.get("logged_in"):
        user = state.get("user") or ""
        log_critical(
            "AUTH_SUCCESS",
            "Google user-present login session detected",
            user=_mask_account(user),
            mode=GOOGLE_SESSION_METHOD,
        )
        return {
            "ok": True,
            "user": user,
            "reason": "user_present_login_completed",
            "method": GOOGLE_SESSION_METHOD,
        }

    return {
        "ok": False,
        "reason": "user_present_login_timeout",
        "method": GOOGLE_SESSION_METHOD,
    }


def ensure_google_login(
    page,
    return_url: str | None = None,
) -> dict[str, Any]:
    """Check Google session and ask the user to log in when needed."""
    original_url = return_url or str(getattr(page, "url", "") or "")
    result = login_google(
        page,
        wait_for_user_s=300,
    )
    if not result.get("ok"):
        return result

    if original_url and "accounts.google.com" not in original_url:
        try:
            page.goto(original_url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2)
        except Exception:  # noqa: BLE001 - 로그인 페이지 확인 후 원래 URL로 되돌아가는 부수 동작 실패는 무시 — 로그인 세션 자체는 건드리지 않음
            pass
    return result


__all__ = [
    "GOOGLE_LOGIN_URL",
    "GOOGLE_SESSION_METHOD",
    "ensure_google_login",
    "login_google",
]
