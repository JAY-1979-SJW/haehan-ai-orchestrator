"""초회 수동 로그인 후 storageState 저장, 이후 세션 재사용.

흐름:
  1. ensure_session(site_name, login_url) 호출
  2. secrets/browser_state/<site_name>.json 이 있으면 → 즉시 경로 반환 (재사용)
  3. 없으면 → headless=False 브라우저 열기 → 사용자 로그인 대기
             → 로그인 완료 감지 → context.storage_state() 저장 → 경로 반환

보안 원칙:
  - 본인 소유 계정에 한해 허용
  - CAPTCHA / 2FA / 봇 탐지 우회 금지
  - storageState 파일은 secrets/ 하위 (.gitignore 대상), 커밋 금지
  - 비밀번호 자동 입력 없음 — 사용자가 직접 입력
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import time as _time_default
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ai_orchestrator.sites import secrets_policy

from .browser_login_probe import (
    _ALLOWED_WAIT_UNTIL,
    _KEEP_OPEN_PROMPT,
    _USER_LOGIN_CONFIRM_PROMPT,
    _classify_login,
    _clip_int,
    _detect_completion,
    _has_strong_reason,
    _initial_is_already_logged_in,
    _normalize_browser_channel,
    _normalize_str_list,
    _observe,
    _safe_bring_to_front,
    _scan_context_pages_aggregate,
)
from .browser_reader import BrowserDependencyMissing, _safe_close
from .web_reader import validate_url_for_readonly_open

logger = logging.getLogger(__name__)

_FIRST_LOGIN_PROMPT = (
    "\n[session-manager] 브라우저 창에서 직접 로그인해 주세요.\n"
    "로그인이 완료된 화면이 보이면 Enter 를 누르세요.\n"
    "(아직 아니면 n + Enter)\n> "
)
_SAVE_CONFIRM_PROMPT = (
    "\n[session-manager] 세션을 저장하고 브라우저를 닫겠습니다. Enter 를 누르세요.\n> "
)

# Login-required URL patterns
_LOGIN_URL_PATTERNS: tuple[str, ...] = (
    "login", "signin", "sign-in", "accounts.", "auth", "oauth",
)

# Login button texts to detect
_LOGIN_BUTTON_TEXTS: tuple[str, ...] = (
    "로그인", "Sign in", "Login", "Log in",
)


@dataclass
class SessionResult:
    ok: bool
    state: str  # "reused" | "captured" | "failed"
    site_name: str
    storage_state_path: Path | None
    login_hint: str = ""
    warnings: list[str] = field(default_factory=list)
    error_code: str = ""
    summary: str = ""


# ── 세션 만료 감지 ────────────────────────────────────────────────────────


def is_login_required_page(page: Any, site_key: str = "") -> tuple[bool, list[str]]:
    """Returns (login_required: bool, evidence: list[str]).

    Detects: password input present, login button visible, account/login URL pattern,
    redirect to login page. Read-only — never clicks or fills.
    """
    evidence: list[str] = []

    # Read page URL (read-only property access)
    try:
        current_url = (getattr(page, "url", "") or "").lower()
    except Exception:
        current_url = ""

    # URL pattern check
    for pattern in _LOGIN_URL_PATTERNS:
        if pattern in current_url:
            evidence.append(f"url_contains:{pattern}")
            break

    # Check for password input via content observation
    try:
        html = page.content() or ""
    except Exception:
        html = ""

    if not isinstance(html, str):
        html = ""

    # Password input detection (read-only HTML parse — never reads values)
    if 'type="password"' in html.lower() or "type='password'" in html.lower():
        evidence.append("password_input_present")

    # Login button text detection
    html_lower = html.lower()
    for btn_text in _LOGIN_BUTTON_TEXTS:
        if btn_text.lower() in html_lower:
            evidence.append(f"login_button_text:{btn_text}")
            break

    # Use existing _observe helper's login_required_hint
    try:
        obs = _observe(page, max_html_chars=200_000)
        if obs.get("login_required_hint"):
            evidence.append("login_required_hint")
        for reason in (obs.get("login_reason") or []):
            r_str = str(reason)
            if r_str not in evidence:
                evidence.append(r_str)
    except Exception:
        pass

    login_required = len(evidence) > 0
    return login_required, evidence


def validate_session_after_reuse(
    page: Any, site_key: str = "", *, target_url: str = ""
) -> dict[str, Any]:
    """Navigate to target_url (or just observe current page) and check if session is valid.

    Returns dict with keys: ok, login_required, evidence, session_expired_detected.
    """
    if target_url:
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            return {
                "ok": False,
                "login_required": False,
                "evidence": [f"navigation_failed:{str(e)[:100]}"],
                "session_expired_detected": False,
            }

    login_required, evidence = is_login_required_page(page, site_key=site_key)
    session_expired = login_required and bool(evidence)

    return {
        "ok": not login_required,
        "login_required": login_required,
        "evidence": evidence,
        "session_expired_detected": session_expired,
    }


def ensure_valid_session(
    site_name: str,
    login_url: str,
    target_url: str,
    *,
    context_factory: Callable[[], Any] | None = None,
    **ensure_kwargs: Any,
) -> SessionResult:
    """ensure_session + open target_url + validate_session_after_reuse.

    If expired: clear_session, re-run ensure_session (capture flow).
    SessionResult gets extra field session_expired_detected: bool in summary.
    """
    result = ensure_session(site_name, login_url, **ensure_kwargs)

    if not result.ok:
        return result

    # Try to validate the session using a browser context
    _browser_factory = ensure_kwargs.get("_browser_factory")
    _clock = ensure_kwargs.get("_clock")

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sp
            factory = _sp
        except ImportError:
            # Cannot validate without playwright — return as-is
            new_summary = result.summary + " [session_expired_detected=unknown]"
            result.summary = new_summary
            return result

    session_expired_detected = False

    try:
        with factory() as pw:
            try:
                storage_state_arg: dict[str, Any] = {}
                if result.storage_state_path and result.storage_state_path.is_file():
                    storage_state_arg["storage_state"] = str(
                        result.storage_state_path
                    )
                browser = pw.chromium.launch(headless=True)
                try:
                    context = browser.new_context(**storage_state_arg)
                    try:
                        page = context.new_page()
                        try:
                            validation = validate_session_after_reuse(
                                page, site_key=site_name, target_url=target_url
                            )
                            session_expired_detected = validation.get(
                                "session_expired_detected", False
                            )
                        finally:
                            _safe_close(page)
                    finally:
                        _safe_close(context)
                finally:
                    _safe_close(browser)
            except Exception as e:
                logger.debug("session validation browse failed: %s", e)
    except Exception as e:
        logger.debug("session validation factory failed: %s", e)

    if session_expired_detected:
        logger.info(
            "session expired detected for %s — clearing and re-capturing",
            site_name,
        )
        clear_session(site_name)
        # Re-run capture (force_relogin=True implied by cleared state)
        recapture_kwargs = {
            k: v for k, v in ensure_kwargs.items()
            if k not in ("_browser_factory", "_clock", "_input_reader")
        }
        recapture_kwargs["_browser_factory"] = _browser_factory
        recapture_kwargs["_clock"] = _clock
        recapture_kwargs["_input_reader"] = ensure_kwargs.get("_input_reader")
        result = ensure_session(site_name, login_url, **recapture_kwargs)
        result.summary = result.summary + " [session_expired_detected=True]"
        return result

    result.summary = result.summary + " [session_expired_detected=False]"
    return result


# ── 파일 권한 보강 ────────────────────────────────────────────────────────


def _secure_state_file(path: Path, warnings: list[str]) -> None:
    """storageState 저장 후 파일 권한 보강 + git-tracked 검사."""
    # git-tracked check — abort if file is tracked
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path)],
            capture_output=True,
            cwd=str(path.parent),
            timeout=5,
        )
        if completed.returncode == 0:
            raise RuntimeError(
                f"storageState file is git-tracked — aborting: {path}"
            )
    except RuntimeError:
        raise
    except Exception:
        pass  # git not available or not a repo — skip check

    # Permission hardening
    system = platform.system()
    if system in ("Linux", "Darwin"):
        try:
            os.chmod(path, 0o600)
            os.chmod(path.parent, 0o700)
        except OSError:
            warnings.append(
                "PERMISSION_WARN: failed to set 0o600 on storageState file"
            )
    else:
        # Windows — best-effort chmod, warn on failure
        try:
            os.chmod(path, 0o600)
        except OSError:
            warnings.append(
                "PERMISSION_WARN_WINDOWS: cannot set restrictive permissions "
                "on storageState file — ensure the directory is access-controlled"
            )


# ── post-login selector check ─────────────────────────────────────────────


def _check_post_login_selectors(page: Any, selectors: list[str]) -> list[str]:
    """Read-only selector check. Returns list of found selectors. Never clicks or fills."""
    found: list[str] = []
    for sel in selectors:
        if not sel or not isinstance(sel, str):
            continue
        try:
            el = page.query_selector(sel)
            if el is not None:
                found.append(sel)
        except Exception:
            pass
    return found


# ── _has_strong_reason_for_capture: url_changed alone is NOT sufficient ──


def _has_strong_reason_for_capture(reasons: list[str]) -> bool:
    """url_changed alone (without at least one other signal) is NOT a strong reason.

    Overrides the browser_login_probe._has_strong_reason rule for capture flow:
    url_changed must be accompanied by at least one other non-success_url_match reason.
    """
    non_url_match: list[str] = [
        r for r in reasons if not r.startswith("success_url_match:")
    ]
    url_changed_only = non_url_match == ["url_changed"]
    if url_changed_only:
        return False
    return _has_strong_reason(reasons)


# ── 공개 API ─────────────────────────────────────────────────────────────


def ensure_session(
    site_name: str,
    login_url: str,
    *,
    wait_seconds: int = 300,
    poll_interval_seconds: int = 3,
    success_url_contains: list[str] | None = None,
    success_text_hints: list[str] | None = None,
    browser_channel: str | None = None,
    force_relogin: bool = False,
    post_login_signals: list[str] | None = None,
    extend_on_activity: bool = True,
    max_extensions: int = 3,
    _browser_factory: Callable[[], Any] | None = None,
    _clock: Any | None = None,
    _input_reader: Callable[[str], str] | None = None,
) -> SessionResult:
    """storageState 재사용 또는 초회 수동 로그인 후 캡처.

    Args:
        site_name:              secrets_policy 기준 사이트 식별자
        login_url:              최초 접속할 로그인 URL
        wait_seconds:           로그인 감지 최대 대기 (초), default 300
        poll_interval_seconds:  관찰 주기 (초)
        success_url_contains:   로그인 완료 판정용 URL 토큰 목록
        success_text_hints:     로그인 완료 판정용 텍스트 힌트 목록
        browser_channel:        chromium / chrome / msedge
        force_relogin:          True 이면 기존 storageState 무시하고 재로그인
        post_login_signals:     로그인 후 확인용 CSS selector 목록 (read-only)
        extend_on_activity:     활동 감지 시 타임아웃 연장 여부
        max_extensions:         최대 연장 횟수
    """
    if not secrets_policy.is_safe_site_name(site_name):
        return SessionResult(
            ok=False, state="failed", site_name=site_name,
            storage_state_path=None, error_code="INVALID_SITE_NAME",
            summary=f"invalid site_name: {site_name!r}",
        )

    state_path = secrets_policy.session_state_path(site_name)

    if not force_relogin and state_path.is_file():
        logger.info("session reused: %s -> %s", site_name, state_path.name)
        return SessionResult(
            ok=True, state="reused", site_name=site_name,
            storage_state_path=state_path,
            summary=f"storageState 재사용: {state_path.name}",
        )

    return _capture_session(
        site_name=site_name,
        login_url=login_url,
        state_path=state_path,
        wait_seconds=wait_seconds,
        poll_interval_seconds=poll_interval_seconds,
        success_url_contains=_normalize_str_list(success_url_contains),
        success_text_hints=_normalize_str_list(success_text_hints),
        browser_channel=browser_channel,
        post_login_signals=list(post_login_signals) if post_login_signals else [],
        extend_on_activity=extend_on_activity,
        max_extensions=max_extensions,
        _browser_factory=_browser_factory,
        _clock=_clock,
        _input_reader=_input_reader,
    )


def clear_session(site_name: str) -> bool:
    """저장된 storageState 파일을 삭제한다. 삭제 성공 여부 반환."""
    try:
        p = secrets_policy.session_state_path(site_name)
        if p.is_file():
            p.unlink()
            logger.info("session cleared: %s", site_name)
            return True
        return False
    except Exception:
        logger.exception("session clear failed: %s", site_name)
        return False


# ── 내부 ─────────────────────────────────────────────────────────────────


def _capture_session(
    *,
    site_name: str,
    login_url: str,
    state_path: Path,
    wait_seconds: int,
    poll_interval_seconds: int,
    success_url_contains: list[str],
    success_text_hints: list[str],
    browser_channel: str | None,
    post_login_signals: list[str],
    extend_on_activity: bool,
    max_extensions: int,
    _browser_factory: Callable[[], Any] | None,
    _clock: Any | None,
    _input_reader: Callable[[str], str] | None,
) -> SessionResult:
    validation = validate_url_for_readonly_open(login_url, allow_private_network=True)
    if not validation.get("ok"):
        return SessionResult(
            ok=False, state="failed", site_name=site_name,
            storage_state_path=None,
            error_code=validation.get("error_code", "URL_INVALID"),
            summary=validation.get("reason", "url validation failed"),
        )

    channel = _normalize_browser_channel(browser_channel)
    if browser_channel is not None and channel is None:
        return SessionResult(
            ok=False, state="failed", site_name=site_name,
            storage_state_path=None,
            error_code="BROWSER_CHANNEL_INVALID",
            summary=f"unknown browser_channel: {browser_channel!r}",
        )

    wait_seconds = _clip_int(wait_seconds, 10, 600, 300)
    poll_interval_seconds = _clip_int(poll_interval_seconds, 1, 30, 3)
    if poll_interval_seconds > wait_seconds:
        poll_interval_seconds = wait_seconds

    time_mod = _clock or _time_default
    input_reader = _input_reader if _input_reader is not None else input

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sp
            factory = _sp
        except ImportError:
            return SessionResult(
                ok=False, state="failed", site_name=site_name,
                storage_state_path=None,
                error_code="BROWSER_DEPENDENCY_MISSING",
                summary="playwright not installed: pip install playwright",
            )

    warnings: list[str] = []

    try:
        return _run_capture(
            factory=factory,
            time_mod=time_mod,
            input_reader=input_reader,
            site_name=site_name,
            login_url=login_url,
            state_path=state_path,
            wait_seconds=wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
            success_urls=success_url_contains,
            success_texts=success_text_hints,
            browser_channel=channel,
            post_login_signals=post_login_signals,
            extend_on_activity=extend_on_activity,
            max_extensions=max_extensions,
            warnings=warnings,
        )
    except BrowserDependencyMissing as e:
        return SessionResult(
            ok=False, state="failed", site_name=site_name,
            storage_state_path=None,
            error_code="BROWSER_DEPENDENCY_MISSING",
            summary=str(e)[:200],
        )
    except Exception as e:
        logger.exception("session capture failed: %s", site_name)
        return SessionResult(
            ok=False, state="failed", site_name=site_name,
            storage_state_path=None,
            error_code="CAPTURE_FAILED",
            summary=str(e)[:200],
        )


def _run_capture(
    *,
    factory: Callable[[], Any],
    time_mod: Any,
    input_reader: Callable[[str], str],
    site_name: str,
    login_url: str,
    state_path: Path,
    wait_seconds: int,
    poll_interval_seconds: int,
    success_urls: list[str],
    success_texts: list[str],
    browser_channel: str | None,
    post_login_signals: list[str],
    extend_on_activity: bool,
    max_extensions: int,
    warnings: list[str],
) -> SessionResult:
    launch_kwargs: dict[str, Any] = {"headless": False}
    if browser_channel and browser_channel != "chromium":
        launch_kwargs["channel"] = browser_channel

    # Hard cap: wait_seconds * (1 + max_extensions)
    hard_cap = wait_seconds * (1 + max(0, max_extensions))

    with factory() as pw:
        try:
            browser = pw.chromium.launch(**launch_kwargs)
        except Exception as e:
            code = (
                "BROWSER_CHANNEL_NOT_AVAILABLE"
                if browser_channel and browser_channel != "chromium"
                else "BROWSER_OPEN_FAILED"
            )
            return SessionResult(
                ok=False, state="failed", site_name=site_name,
                storage_state_path=None, error_code=code, summary=str(e)[:200],
            )

        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
                    _safe_bring_to_front(page)

                    initial = _observe(page, max_html_chars=500_000)

                    # 관찰 루프 — timeout hardening
                    deadline_ts = time_mod.monotonic() + wait_seconds
                    hard_deadline_ts = time_mod.monotonic() + hard_cap
                    last_obs = initial
                    completed_reasons: list[str] = []
                    extensions_used = 0
                    sixty_second_warned = False

                    # Track activity signals for extension
                    last_url = initial.get("current_url", "")
                    last_login_hint = initial.get("login_required_hint", False)

                    while True:
                        now = time_mod.monotonic()

                        # Hard cap enforcement
                        if now >= hard_deadline_ts:
                            break

                        # Soft deadline check
                        if now >= deadline_ts:
                            # Check for activity-based extension
                            if (
                                extend_on_activity
                                and extensions_used < max_extensions
                            ):
                                cur_url = last_obs.get("current_url", "")
                                cur_hint = last_obs.get("login_required_hint", False)
                                activity = (
                                    cur_url != last_url
                                    or cur_hint != last_login_hint
                                )
                                if activity:
                                    extension_secs = poll_interval_seconds * 5
                                    # Don't extend past hard cap
                                    new_deadline = min(
                                        deadline_ts + extension_secs,
                                        hard_deadline_ts,
                                    )
                                    if new_deadline > deadline_ts:
                                        deadline_ts = new_deadline
                                        extensions_used += 1
                                        logger.info(
                                            "로그인 대기 시간 연장 (%d/%d): +%ds",
                                            extensions_used,
                                            max_extensions,
                                            extension_secs,
                                        )
                                        last_url = cur_url
                                        last_login_hint = cur_hint
                                        continue
                            break

                        # 60 seconds remaining warning
                        remaining = deadline_ts - now
                        if remaining <= 60 and not sixty_second_warned:
                            sixty_second_warned = True
                            logger.warning("로그인 대기 시간이 60초 남았습니다")

                        sleep_for = min(poll_interval_seconds, deadline_ts - now)
                        if sleep_for > 0:
                            time_mod.sleep(sleep_for)
                        last_obs = _observe(page, max_html_chars=500_000)
                        completed_reasons = _detect_completion(
                            initial=initial, current=last_obs,
                            success_urls=success_urls, success_texts=success_texts,
                        )
                        if _has_strong_reason_for_capture(completed_reasons):
                            break

                        # Update activity baseline
                        last_url = last_obs.get("current_url", last_url)
                        last_login_hint = last_obs.get(
                            "login_required_hint", last_login_hint
                        )

                    # post_login_signals check (read-only, evidence only)
                    post_login_found: list[str] = []
                    if post_login_signals:
                        post_login_found = _check_post_login_selectors(
                            page, post_login_signals
                        )
                        if post_login_found:
                            for sel in post_login_found:
                                completed_reasons.append(
                                    f"post_login_selector_found:{sel[:80]}"
                                )
                        else:
                            warnings.append(
                                "POST_LOGIN_SELECTOR_NOT_FOUND: "
                                "none of post_login_signals found — "
                                "session may not be fully loaded yet"
                            )

                    # 사용자 로그인 완료 확인
                    login_confirmed = False
                    try:
                        answer = input_reader(_FIRST_LOGIN_PROMPT)
                        stripped = (answer or "").strip().lower()
                        if stripped not in {"n", "no", "아니오"}:
                            login_confirmed = True
                            if "user_confirmed_login" not in completed_reasons:
                                completed_reasons.append("user_confirmed_login")
                    except (KeyboardInterrupt, EOFError):
                        return SessionResult(
                            ok=False, state="failed", site_name=site_name,
                            storage_state_path=None,
                            error_code="USER_CANCELED",
                            summary="사용자가 취소했습니다",
                        )

                    initial_already = _initial_is_already_logged_in(
                        initial=initial, success_urls=success_urls,
                    )
                    login_state_hint, login_completed_hint = _classify_login(
                        initial=initial,
                        completion_reasons=completed_reasons,
                        initial_is_already_logged_in=initial_already,
                        require_user_login_confirm=True,
                        login_confirmed_by_user=login_confirmed,
                    )

                    pages_count, success_across = _scan_context_pages_aggregate(
                        context=context, success_urls=success_urls,
                    )

                    if not login_completed_hint:
                        return SessionResult(
                            ok=False, state="failed", site_name=site_name,
                            storage_state_path=None,
                            login_hint=login_state_hint,
                            error_code="LOGIN_NOT_CONFIRMED",
                            summary=(
                                f"로그인 완료가 확인되지 않았습니다 "
                                f"(hint={login_state_hint})"
                            ),
                            warnings=list(warnings),
                        )

                    # storageState 저장
                    try:
                        input_reader(_SAVE_CONFIRM_PROMPT)
                    except (KeyboardInterrupt, EOFError):
                        pass

                    state_path.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(state_path))
                    logger.info(
                        "storageState saved: %s -> %s", site_name, state_path.name,
                    )
                    _warn_gitignore(state_path, warnings)
                    _secure_state_file(state_path, warnings)

                    return SessionResult(
                        ok=True, state="captured", site_name=site_name,
                        storage_state_path=state_path,
                        login_hint=login_state_hint,
                        warnings=list(warnings),
                        summary=(
                            f"storageState 저장 완료: {state_path.name} "
                            f"(reasons={','.join(completed_reasons)})"
                        ),
                    )
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _warn_gitignore(state_path: Path, warnings: list[str]) -> None:
    """secrets/ 가 .gitignore 에 없으면 경고."""
    try:
        root = state_path.parent.parent.parent  # secrets/ 의 repo root
        gitignore = root / ".gitignore"
        if not gitignore.is_file():
            warnings.append("GITIGNORE_MISSING: .gitignore 파일을 찾을 수 없습니다")
            return
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        lines = [ln.strip() for ln in content.splitlines()]
        covered = any(
            ln in {"secrets/", "secrets", "/secrets", "/secrets/"}
            for ln in lines
        )
        if not covered:
            warnings.append(
                "GITIGNORE_NOT_COVERED: secrets/ 가 .gitignore 에 없습니다 — "
                "storageState 파일이 커밋될 위험이 있습니다"
            )
    except Exception:
        logger.debug("gitignore check failed", exc_info=True)


__all__ = [
    "SessionResult",
    "ensure_session",
    "clear_session",
    "is_login_required_page",
    "validate_session_after_reuse",
    "ensure_valid_session",
]
