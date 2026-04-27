"""Playwright 기반 read-only 실행기.

원칙:
- 클릭 / 입력 / 제출 / 선택 / 체크 / 다운로드 / 업로드 / 로그인 / 회원가입 금지
- URL 열기와 DOM 메타데이터 읽기까지만 허용
- 동시 브라우저 인스턴스는 1개 제한
"""
from __future__ import annotations

import json
import logging
import platform
import socket
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

from . import config as _cfg
from . import errors as _err

logger = logging.getLogger(__name__)

# 동시 브라우저 1개 제한용 락. 실제 브라우저 action 에서만 사용.
_browser_lock = threading.Lock()

# 로그에 남기면 안 되는 키 (부분 일치, 대소문자 무관)
_SENSITIVE_KEY_PARTS = (
    "password",
    "token",
    "cookie",
    "authorization",
    "session",
    "secret",
    "apikey",
    "api_key",
)


# ── 시간/안전 실행 헬퍼 ─────────────────────────────────────────────
def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 - Playwright 예외 타입이 다양
        return default


# ── 민감정보 스크러빙 ───────────────────────────────────────────────
def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    low = key.lower()
    return any(s in low for s in _SENSITIVE_KEY_PARTS)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if not _is_sensitive_key(k)}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _safe_url(url: str) -> str:
    """URL 로깅 시 userinfo(user:pass@) 제거."""
    if not isinstance(url, str) or not url:
        return ""
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    if not p.hostname:
        return url
    netloc = p.hostname
    if p.port:
        netloc = f"{p.hostname}:{p.port}"
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


# ── 로그 기록 ───────────────────────────────────────────────────────
def log_event(entry: dict) -> None:
    """agent_actions.jsonl 에 한 줄 append.

    entry 에 민감 키가 섞여 들어오더라도 _sanitize 로 제거한 뒤 기록.
    target_url 은 userinfo 가 제거된 형태로만 남긴다.
    """
    safe_entry = dict(entry)
    if "target_url" in safe_entry:
        safe_entry["target_url"] = _safe_url(safe_entry.get("target_url") or "")
    safe_entry = _sanitize(safe_entry)

    path = _cfg.AGENT_LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("agent log write failed: %s", e)


# ── 시스템 정보 / ping ──────────────────────────────────────────────
def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _chromium_available() -> bool:
    """sync_api 가 import 가능하면 chromium 인터페이스 접근 가능으로 본다.

    실제 바이너리 존재 여부까지 조회하려면 sync_playwright 를 런치해야 해
    비용이 크므로, 현 단계에서는 import 가능성을 프록시로 사용.
    """
    if not _playwright_available():
        return False
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def ping() -> dict:
    return {"pong": True, "fetched_at": _iso_now()}


def get_system_info() -> dict:
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "playwright_available": _playwright_available(),
        "chromium_available": _chromium_available(),
        "fetched_at": _iso_now(),
    }


# ── 브라우저 read-only 세션 ─────────────────────────────────────────
def browser_readonly(
    url: str,
    *,
    inspect: bool,
    timeout_ms: int = _cfg.DEFAULT_GOTO_TIMEOUT_MS,
    snippet_max_chars: int = _cfg.SNIPPET_MAX_CHARS,
    headless: bool = _cfg.HEADLESS,
) -> tuple[Optional[dict], Optional[str]]:
    """Playwright 로 URL 을 열고 read-only 필드만 수집한다.

    반환: (data_or_None, error_or_None)
      - 성공: data = {"final_url", "title"}(+ inspect 시 snippet/counts)
      - 실패: error 문자열. 민감정보 없음.
    """
    try:
        from playwright.sync_api import (  # type: ignore
            sync_playwright,
            TimeoutError as PwTimeoutError,
        )
    except ImportError:
        return None, _err.PLAYWRIGHT_NOT_INSTALLED

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        timed_out = False
                        try:
                            page.goto(
                                url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            timed_out = True

                        if timed_out:
                            return None, _err.PLAYWRIGHT_TIMEOUT

                        final_url = _safe(lambda: page.url or url, url)
                        title = _safe(
                            lambda: (page.title() or "").strip(), ""
                        )
                        data: dict = {"final_url": final_url, "title": title}

                        if inspect:
                            body_text = _safe(
                                lambda: page.locator("body").inner_text(
                                    timeout=timeout_ms
                                ) or "",
                                "",
                            )
                            data["snippet"] = body_text[:snippet_max_chars]
                            data["input_count"] = _safe(
                                lambda: page.locator("input").count(), 0
                            )
                            data["button_count"] = _safe(
                                lambda: page.locator("button").count(), 0
                            )
                            data["link_count"] = _safe(
                                lambda: page.locator("a").count(), 0
                            )
                        return data, None
                    finally:
                        _safe(page.close, None)
                finally:
                    _safe(context.close, None)
            finally:
                _safe(browser.close, None)
    except PwTimeoutError:
        return None, _err.PLAYWRIGHT_TIMEOUT
    except Exception as e:  # noqa: BLE001
        logger.warning("browser_readonly error | %s", e)
        return None, _err.with_reason(_err.PLAYWRIGHT_ERROR, type(e).__name__)


# ── 로그인 (최소 범위: fill username/password + submit 1회 + success check) ──
def _evaluate_success(page, check, final_url: str, timeout_ms: int) -> bool:
    """success_check 기준에 따라 로그인 성공 여부를 판정한다."""
    kind = check.kind
    if kind == "url":
        return isinstance(final_url, str) and (check.value in final_url)
    if kind == "selector":
        count = _safe(lambda: page.locator(check.value).count(), 0)
        return bool(count and count > 0)
    if kind == "text":
        body = _safe(
            lambda: page.locator("body").inner_text(timeout=timeout_ms) or "",
            "",
        )
        return isinstance(body, str) and (check.value in body)
    return False


def login_with_secret(
    site_key: str,
    *,
    timeout_ms: int = _cfg.DEFAULT_GOTO_TIMEOUT_MS,
    headless: bool = _cfg.HEADLESS,
) -> tuple[Optional[dict], Optional[str]]:
    """시크릿 스토어에 저장된 계정으로 로그인 **성공 여부 확인까지만** 수행.

    허용 동작: ``page.goto`` / username·password ``fill`` / submit ``click`` 1회 /
    성공 판정용 URL·selector·text 읽기.
    금지 동작: 회원가입, 추가 폼 제출, 설정 변경, 다운로드, 업로드, 임의 클릭,
    다단계 workflow 진행.

    반환: ``(data, error)``
      - 성공 판정: data = {site_key, login_url, final_url, login_success, checked_by}
      - 실패 판정: data 는 동일 형식, login_success=False 이며 error 가 세팅됨
      - 선결 오류(프로필/시크릿/URL 정책): data = None, error 세팅
    """
    from .policy import validate_url
    from .secrets import store as _secret_store
    from . import site_profiles as _sp

    profile = _sp.get_profile(site_key)
    if profile is None:
        return None, _err.SITE_PROFILE_NOT_FOUND

    # 1) login_url 이 외부 공개 http/https 인지 (localhost/private/file:// 차단)
    ok, reason = validate_url(profile.login_url)
    if not ok:
        return None, _err.with_reason(_err.LOGIN_URL_NOT_ALLOWED, reason)

    # 2) host whitelist (프로필이 명시한 allowed_hosts 만 허용)
    if not _sp.is_host_allowed(profile, profile.login_url):
        return None, _err.HOST_NOT_ALLOWED

    # 3) 시크릿 조회 — 평문은 이 함수 스코프 내에서만 존재
    try:
        sec = _secret_store._get_secret_plain_internal(site_key)
    except Exception as e:  # noqa: BLE001 - crypto/IO 에러 포괄
        return None, _err.with_reason(_err.SECRET_STORE_ERROR, type(e).__name__)
    if sec is None:
        return None, _err.SECRET_NOT_FOUND

    try:
        from playwright.sync_api import (  # type: ignore
            sync_playwright,
            TimeoutError as PwTimeoutError,
        )
    except ImportError:
        return None, _err.PLAYWRIGHT_NOT_INSTALLED

    data_shell = {
        "site_key": site_key,
        "login_url": profile.login_url,
        "final_url": profile.login_url,
        "login_success": False,
        "checked_by": profile.success_check.kind,
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        try:
                            page.goto(
                                profile.login_url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            return data_shell, _err.PLAYWRIGHT_TIMEOUT

                        # 이번 단계 허용 동작: fill / fill / click (1회)
                        try:
                            page.fill(
                                profile.username_selector,
                                sec.username,
                                timeout=timeout_ms,
                            )
                            page.fill(
                                profile.password_selector,
                                sec.password,
                                timeout=timeout_ms,
                            )
                            page.click(
                                profile.submit_selector,
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            return data_shell, _err.SELECTOR_TIMEOUT

                        # 제출 후 페이지 안정화 — 최선 노력, 실패해도 무시
                        _safe(
                            lambda: page.wait_for_load_state(
                                "domcontentloaded", timeout=timeout_ms
                            ),
                            None,
                        )

                        final_url = _safe(
                            lambda: page.url or profile.login_url, profile.login_url
                        )
                        success = _evaluate_success(
                            page, profile.success_check, final_url, timeout_ms
                        )

                        data = {
                            "site_key": site_key,
                            "login_url": profile.login_url,
                            "final_url": final_url,
                            "login_success": bool(success),
                            "checked_by": profile.success_check.kind,
                        }
                        return data, None
                    finally:
                        _safe(page.close, None)
                finally:
                    _safe(context.close, None)
            finally:
                _safe(browser.close, None)
    except PwTimeoutError:
        return data_shell, _err.PLAYWRIGHT_TIMEOUT
    except Exception as e:  # noqa: BLE001
        logger.warning("login_with_secret error | %s", type(e).__name__)
        return data_shell, _err.with_reason(_err.PLAYWRIGHT_ERROR, type(e).__name__)
    finally:
        # 참조 해제(파이썬 문자열은 in-place wipe 불가하지만 생존 시간 최소화).
        sec = None  # noqa: F841


# ── inspect_after_login 보조: 2단계 구조화 추출 ────────────────────────
# 허용: count / nth / inner_text / get_attribute 까지. 모두 읽기 전용.
# 금지: click / fill / evaluate / route / add_init_script / screenshot 등.
_TOP_ITEMS_MAX = 10
_TOP_TEXT_MAX = 200
_TOP_HREF_MAX = 500
_HEADING_SELECTOR = "h1, h2, h3"


def _collect_top_links(page, *, timeout_ms: int) -> list[dict]:
    """문서 순서 상위 링크 최대 10개의 text/href 만 수집 (클릭 없음)."""
    try:
        loc = page.locator("a")
    except Exception:  # noqa: BLE001
        return []
    total = _safe(lambda: loc.count(), 0)
    n = min(int(total or 0), _TOP_ITEMS_MAX)
    items: list[dict] = []
    for i in range(n):
        el = _safe(lambda i=i: loc.nth(i), None)
        if el is None:
            continue
        text = _safe(
            lambda el=el: (el.inner_text(timeout=timeout_ms) or "").strip(),
            "",
        )
        href = _safe(lambda el=el: el.get_attribute("href") or "", "")
        items.append({
            "text": (text or "")[:_TOP_TEXT_MAX],
            "href": (href or "")[:_TOP_HREF_MAX],
        })
    return items


def _collect_top_buttons(page, *, timeout_ms: int) -> list[dict]:
    """상위 버튼 최대 10개의 보이는 텍스트만 수집 (클릭 없음)."""
    try:
        loc = page.locator("button")
    except Exception:  # noqa: BLE001
        return []
    total = _safe(lambda: loc.count(), 0)
    n = min(int(total or 0), _TOP_ITEMS_MAX)
    items: list[dict] = []
    for i in range(n):
        el = _safe(lambda i=i: loc.nth(i), None)
        if el is None:
            continue
        text = _safe(
            lambda el=el: (el.inner_text(timeout=timeout_ms) or "").strip(),
            "",
        )
        items.append({"text": (text or "")[:_TOP_TEXT_MAX]})
    return items


def _classify_page_kind(
    *,
    link_count: int,
    button_count: int,
    table_count: int,
    heading_count: int,
    form_count: int,
    visible_text_length: int,
) -> str:
    """단순 휴리스틱. 규칙은 아래 순서로 확인한다 (설명 가능성 우선)."""
    # 1) list_page: 테이블 1개 이상 + 링크 다수
    if table_count >= 1 and link_count >= 10:
        return "list_page"
    # 2) dashboard: 버튼/링크 다수, 테이블 적음
    if button_count >= 5 and link_count >= 10 and table_count <= 1:
        return "dashboard"
    # 3) detail_page: 제목 + 본문 길이, 테이블 적음, 링크 적음
    if (
        heading_count >= 1
        and table_count <= 1
        and visible_text_length >= 500
        and link_count < 10
    ):
        return "detail_page"
    # 4) login_result: 매우 가벼운 포스트-로그인 페이지
    if (
        visible_text_length <= 200
        and link_count <= 5
        and button_count <= 3
        and table_count == 0
    ):
        return "login_result"
    return "unknown"


# ── 로그인 후 탐색 (inspect_after_login) ───────────────────────────────
# 허용: goto(login_url) / fill(user,pass) / click(submit) 1회 /
#       goto(target_url) / URL·title·selector·body·링크·버튼 "읽기" 까지.
# 금지: 추가 click, fill, submit, check, select_option, download, upload,
#       screenshot, evaluate 쓰기성 스크립트 주입, 임의 링크 클릭.
def inspect_after_login(
    site_key: str,
    target_url: str,
    *,
    timeout_ms: int = _cfg.DEFAULT_GOTO_TIMEOUT_MS,
    snippet_max_chars: int = _cfg.SNIPPET_MAX_CHARS,
    headless: bool = _cfg.HEADLESS,
) -> tuple[Optional[dict], Optional[str]]:
    """시크릿으로 로그인 후 ``target_url`` 에 이동해 읽기 전용 정보만 수집.

    반환: ``(data, error)``
      - 성공 : data = {site_key, login_url, login_success=True, target_url, final_url,
                        title, snippet, input_count, button_count, link_count,
                        table_count, checked_by[, inspect_checked_by]}, error=None
      - 로그인 실패/타임아웃/검증 실패 : data = shell(최소 정보), error 세팅
      - 선결 오류(프로필/시크릿/URL 정책) : data = None, error 세팅
    """
    from .policy import validate_url
    from .secrets import store as _secret_store
    from . import site_profiles as _sp

    profile = _sp.get_profile(site_key)
    if profile is None:
        return None, _err.SITE_PROFILE_NOT_FOUND

    # 1) login_url 검증 (localhost/private/file:// 차단 유지)
    ok, reason = validate_url(profile.login_url)
    if not ok:
        return None, _err.with_reason(_err.LOGIN_URL_NOT_ALLOWED, reason)
    if not _sp.is_host_allowed(profile, profile.login_url):
        return None, _err.LOGIN_HOST_NOT_ALLOWED

    # 2) target_url 검증 — host whitelist + (선택) path whitelist
    if not isinstance(target_url, str) or not target_url.strip():
        return None, _err.TARGET_URL_REQUIRED
    ok, reason = validate_url(target_url)
    if not ok:
        return None, _err.with_reason(_err.TARGET_URL_NOT_ALLOWED, reason)
    if not _sp.is_host_allowed(profile, target_url):
        return None, _err.TARGET_HOST_NOT_ALLOWED
    if not _sp.is_target_path_allowed(profile, target_url):
        return None, _err.TARGET_PATH_NOT_ALLOWED

    # 3) 시크릿 복원 — 평문은 이 함수 스코프 내에서만 존재
    try:
        sec = _secret_store._get_secret_plain_internal(site_key)
    except Exception as e:  # noqa: BLE001
        return None, _err.with_reason(_err.SECRET_STORE_ERROR, type(e).__name__)
    if sec is None:
        return None, _err.SECRET_NOT_FOUND

    try:
        from playwright.sync_api import (  # type: ignore
            sync_playwright,
            TimeoutError as PwTimeoutError,
        )
    except ImportError:
        return None, _err.PLAYWRIGHT_NOT_INSTALLED

    shell = {
        "site_key": site_key,
        "login_url": profile.login_url,
        "target_url": target_url,
        "login_success": False,
        "checked_by": profile.success_check.kind,
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        # ─ 로그인 단계 ─
                        try:
                            page.goto(
                                profile.login_url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            return shell, _err.LOGIN_GOTO_TIMEOUT

                        try:
                            page.fill(
                                profile.username_selector,
                                sec.username,
                                timeout=timeout_ms,
                            )
                            page.fill(
                                profile.password_selector,
                                sec.password,
                                timeout=timeout_ms,
                            )
                            page.click(
                                profile.submit_selector,
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            return shell, _err.LOGIN_SELECTOR_TIMEOUT

                        _safe(
                            lambda: page.wait_for_load_state(
                                "domcontentloaded", timeout=timeout_ms
                            ),
                            None,
                        )

                        post_login_url = _safe(
                            lambda: page.url or profile.login_url,
                            profile.login_url,
                        )
                        login_success = _evaluate_success(
                            page, profile.success_check, post_login_url, timeout_ms
                        )
                        shell["login_success"] = bool(login_success)

                        if not login_success:
                            return shell, _err.LOGIN_FAILED

                        # ─ target 이동 (읽기 전용) ─
                        try:
                            page.goto(
                                target_url,
                                wait_until="domcontentloaded",
                                timeout=timeout_ms,
                            )
                        except PwTimeoutError:
                            shell["final_url"] = post_login_url
                            return shell, _err.TARGET_GOTO_TIMEOUT

                        final_url = _safe(
                            lambda: page.url or target_url, target_url
                        )

                        # (선택) inspect_success_check
                        inspect_checked_by: Optional[str] = None
                        if profile.inspect_success_check is not None:
                            inspect_checked_by = profile.inspect_success_check.kind
                            if not _evaluate_success(
                                page,
                                profile.inspect_success_check,
                                final_url,
                                timeout_ms,
                            ):
                                shell["final_url"] = final_url
                                shell["inspect_checked_by"] = inspect_checked_by
                                return shell, _err.INSPECT_CHECK_FAILED

                        # ─ 읽기 전용 필드 수집 ─
                        title = _safe(lambda: (page.title() or "").strip(), "")
                        body_text = _safe(
                            lambda: page.locator("body").inner_text(
                                timeout=timeout_ms
                            )
                            or "",
                            "",
                        )
                        input_count = int(_safe(
                            lambda: page.locator("input").count(), 0
                        ) or 0)
                        button_count = int(_safe(
                            lambda: page.locator("button").count(), 0
                        ) or 0)
                        link_count = int(_safe(
                            lambda: page.locator("a").count(), 0
                        ) or 0)
                        table_count = int(_safe(
                            lambda: page.locator("table").count(), 0
                        ) or 0)
                        heading_count = int(_safe(
                            lambda: page.locator(_HEADING_SELECTOR).count(), 0
                        ) or 0)
                        form_count = int(_safe(
                            lambda: page.locator("form").count(), 0
                        ) or 0)
                        visible_text_length = len(body_text or "")

                        top_links = _collect_top_links(
                            page, timeout_ms=timeout_ms
                        )
                        top_buttons = _collect_top_buttons(
                            page, timeout_ms=timeout_ms
                        )
                        page_kind = _classify_page_kind(
                            link_count=link_count,
                            button_count=button_count,
                            table_count=table_count,
                            heading_count=heading_count,
                            form_count=form_count,
                            visible_text_length=visible_text_length,
                        )

                        data = {
                            "site_key": site_key,
                            "login_url": profile.login_url,
                            "login_success": True,
                            "target_url": target_url,
                            "final_url": final_url,
                            "title": title,
                            "snippet": body_text[:snippet_max_chars],
                            "input_count": input_count,
                            "button_count": button_count,
                            "link_count": link_count,
                            "table_count": table_count,
                            "heading_count": heading_count,
                            "form_count": form_count,
                            "visible_text_length": visible_text_length,
                            "top_links": top_links,
                            "top_buttons": top_buttons,
                            "page_kind": page_kind,
                            "checked_by": profile.success_check.kind,
                        }
                        if inspect_checked_by:
                            data["inspect_checked_by"] = inspect_checked_by
                        return data, None
                    finally:
                        _safe(page.close, None)
                finally:
                    _safe(context.close, None)
            finally:
                _safe(browser.close, None)
    except PwTimeoutError:
        return shell, _err.PLAYWRIGHT_TIMEOUT
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect_after_login error | %s", type(e).__name__)
        return shell, _err.with_reason(_err.PLAYWRIGHT_ERROR, type(e).__name__)
    finally:
        sec = None  # noqa: F841


__all__ = [
    "ping",
    "get_system_info",
    "browser_readonly",
    "login_with_secret",
    "inspect_after_login",
    "log_event",
    "_browser_lock",
    "_iso_now",
    "_safe_url",
]
