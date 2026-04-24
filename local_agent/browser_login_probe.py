"""local_agent 수동 로그인 확인 모드 (Stage 3 smoke probe).

실제 브라우저를 ``headless=False`` 로 열어 지정 URL 에 접속한 뒤, 사용자가
직접 로그인하는 동안 ``page.url`` / ``page.title`` / ``page.content`` 만
주기적으로 read-only 로 관찰해 "로그인 완료로 보이는 화면 변화" 가 발생
했는지 추정한다. 반환 dict 는 HTML 원문 전체/쿠키/세션/password 값을
포함하지 않는다.

절대 수행하지 않는 것:
  - 아이디/비밀번호 자동 입력 (page.fill / page.type / page.press)
  - 클릭/제출/파일업로드 (page.click / page.select_option / page.set_input_files)
  - evaluate 로 자바스크립트 주입
  - 쿠키 / storage_state / localStorage / sessionStorage 수집
  - password / hidden input value 수집
  - screenshot 저장

테스트 편의를 위해 ``_browser_factory`` 와 ``_clock`` 을 주입할 수 있다.
None 이면 실제 ``playwright.sync_api.sync_playwright`` 와 ``time`` 표준
모듈이 사용된다.
"""
from __future__ import annotations

import logging
import time as _time_default
from typing import Any, Callable

from .browser_reader import (
    BrowserDependencyMissing,
    _detect_login_required,
    _safe_close,
)
from .web_reader import analyze_html_structure, validate_url_for_readonly_open

logger = logging.getLogger(__name__)


_ALLOWED_WAIT_UNTIL: frozenset[str] = frozenset({
    "domcontentloaded", "load", "networkidle", "commit",
})

_MIN_WAIT_SECONDS = 1
_MAX_WAIT_SECONDS = 600
_MIN_POLL_SECONDS = 1
_MAX_POLL_SECONDS = 30
_DEFAULT_MAX_HTML = 500_000
_MAX_HTML_CAP = 2_000_000


def probe_manual_login_flow(
    url: str,
    *,
    wait_seconds: int = 120,
    poll_interval_seconds: int = 3,
    success_url_contains: list[str] | None = None,
    success_text_hints: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    allow_private_network: bool = False,
    max_html_chars: int = _DEFAULT_MAX_HTML,
    wait_until: str = "domcontentloaded",
    goto_timeout_ms: int = 15000,
    _browser_factory: Callable[[], Any] | None = None,
    _clock: Any | None = None,
) -> dict[str, Any]:
    """수동 로그인 확인 모드. 사용자가 직접 로그인하는 동안 read-only 관찰.

    어떤 경우에도 ID/PW 자동 입력, 클릭, 쿠키/스토리지 수집을 수행하지
    않는다. wait_seconds 타임아웃 내에 로그인 완료로 추정되는 화면 변화가
    감지되면 ``ok=True`` 로, 그렇지 않으면 ``ok=False`` /
    ``error_code="LOGIN_TIMEOUT"`` 로 반환한다.
    """
    # 1) URL 안전성 (http/https + 공개 호스트).
    validation = validate_url_for_readonly_open(
        url, allow_private_network=allow_private_network,
    )
    if not validation.get("ok"):
        return _err(
            url=url,
            error_code=validation.get("error_code", "URL_INVALID"),
            reason=validation.get("reason", "url validation failed"),
        )

    # 2) allowed_hosts 화이트리스트 검사.
    allowed = _normalize_allowed_hosts(allowed_hosts)
    host = validation.get("host", "")
    if allowed is not None and not _host_allowed(host, allowed):
        return _err(
            url=url,
            error_code="HOST_NOT_ALLOWED",
            reason=f"host not in allowed_hosts: {host}",
        )

    # 3) 파라미터 정규화.
    if wait_until not in _ALLOWED_WAIT_UNTIL:
        wait_until = "domcontentloaded"
    wait_seconds = _clip_int(
        wait_seconds, _MIN_WAIT_SECONDS, _MAX_WAIT_SECONDS, 120,
    )
    poll_interval_seconds = _clip_int(
        poll_interval_seconds, _MIN_POLL_SECONDS, _MAX_POLL_SECONDS, 3,
    )
    if poll_interval_seconds > wait_seconds:
        poll_interval_seconds = wait_seconds
    max_html_chars = _clip_int(
        max_html_chars, 1000, _MAX_HTML_CAP, _DEFAULT_MAX_HTML,
    )
    goto_timeout_ms = _clip_int(goto_timeout_ms, 1000, 60000, 15000)

    success_urls = _normalize_str_list(success_url_contains)
    success_texts = _normalize_str_list(success_text_hints)

    time_mod = _clock or _time_default

    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright
        except ImportError:
            return _err(
                url=url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                reason="playwright not installed: pip install playwright",
            )
        factory = _sync_playwright

    warnings: list[str] = []

    try:
        return _run_probe(
            factory=factory,
            time_mod=time_mod,
            url=url,
            wait_until=wait_until,
            goto_timeout_ms=goto_timeout_ms,
            wait_seconds=wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
            max_html_chars=max_html_chars,
            success_urls=success_urls,
            success_texts=success_texts,
            warnings=warnings,
        )
    except BrowserDependencyMissing as e:
        return _err(
            url=url, error_code="BROWSER_DEPENDENCY_MISSING",
            reason=str(e)[:200],
        )
    except Exception as e:  # pragma: no cover - 실제 환경 오류
        logger.exception("manual login probe failed")
        return _err(
            url=url, error_code="BROWSER_OPEN_FAILED", reason=str(e)[:200],
        )


# ── 내부 ────────────────────────────────────────────────────────────────

def _run_probe(
    *,
    factory: Callable[[], Any],
    time_mod: Any,
    url: str,
    wait_until: str,
    goto_timeout_ms: int,
    wait_seconds: int,
    poll_interval_seconds: int,
    max_html_chars: int,
    success_urls: list[str],
    success_texts: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    with factory() as pw:
        browser = pw.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    page.goto(
                        url, wait_until=wait_until, timeout=goto_timeout_ms,
                    )

                    initial = _observe(page, max_html_chars=max_html_chars)
                    deadline_ts = time_mod.monotonic() + wait_seconds

                    last_obs = initial
                    completed_reasons: list[str] = []
                    completed = False

                    while True:
                        now = time_mod.monotonic()
                        if now >= deadline_ts:
                            break
                        sleep_for = min(
                            poll_interval_seconds, deadline_ts - now,
                        )
                        if sleep_for > 0:
                            time_mod.sleep(sleep_for)
                        last_obs = _observe(
                            page, max_html_chars=max_html_chars,
                        )
                        completed_reasons = _detect_completion(
                            initial=initial,
                            current=last_obs,
                            success_urls=success_urls,
                            success_texts=success_texts,
                        )
                        if completed_reasons:
                            completed = True
                            break

                    if completed:
                        return {
                            "ok": True,
                            "mode": "manual_login_probe",
                            "url": url,
                            "initial": _redact_observation(
                                initial, include_structure=False,
                            ),
                            "after": _redact_observation(
                                last_obs,
                                include_structure=True,
                                login_completed_hint=True,
                                login_completion_reason=completed_reasons,
                            ),
                            "summary": (
                                "manual login completed hint=true reasons="
                                + ",".join(completed_reasons)
                            )[:300],
                            "warnings": warnings,
                        }

                    return {
                        "ok": False,
                        "mode": "manual_login_probe",
                        "url": url,
                        "error_code": "LOGIN_TIMEOUT",
                        "summary": (
                            "Manual login was not detected before timeout"
                        ),
                        "initial": _redact_observation(
                            initial, include_structure=False,
                        ),
                        "last_observation": _redact_observation(
                            last_obs,
                            include_structure=False,
                            login_completed_hint=False,
                        ),
                        "warnings": warnings,
                    }
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _observe(page: Any, *, max_html_chars: int) -> dict[str, Any]:
    """read-only 관찰 1회. 오직 title / url / content 만 호출."""
    title = page.title() or ""
    current_url = page.url or ""
    html = page.content() or ""
    if not isinstance(html, str):
        html = ""
    html_truncated = False
    if len(html) > max_html_chars:
        html = html[:max_html_chars]
        html_truncated = True
    structure = analyze_html_structure(html=html, base_url=current_url)
    login_hint, login_reason = _detect_login_required(structure)
    return {
        "title": (title or "")[:300],
        "current_url": (current_url or "")[:500],
        "html_truncated": html_truncated,
        "login_required_hint": login_hint,
        "login_reason": login_reason,
        "page_structure": structure,
    }


def _detect_completion(
    *,
    initial: dict[str, Any],
    current: dict[str, Any],
    success_urls: list[str],
    success_texts: list[str],
) -> list[str]:
    """로그인 완료로 보이는 구조 변화 감지."""
    reasons: list[str] = []

    initial_pw = "password_input_detected" in (
        initial.get("login_reason") or []
    )
    current_pw = "password_input_detected" in (
        current.get("login_reason") or []
    )
    if initial_pw and not current_pw:
        reasons.append("password_input_disappeared")

    if initial.get("current_url") and current.get("current_url"):
        if initial["current_url"] != current["current_url"]:
            reasons.append("url_changed")

    if initial.get("login_required_hint") and not current.get(
        "login_required_hint"
    ):
        reasons.append("login_required_hint_cleared")

    cur_url = current.get("current_url") or ""
    for tok in success_urls:
        if tok and tok in cur_url:
            reasons.append(f"success_url_match:{tok[:60]}")
            break

    text_blob = _visible_text_blob(current.get("page_structure") or {})
    for tok in success_texts:
        if tok and tok in text_blob:
            reasons.append(f"success_text_match:{tok[:60]}")
            break

    # de-dup, keep order.
    seen: set[str] = set()
    unique: list[str] = []
    for r in reasons:
        if r in seen:
            continue
        seen.add(r)
        unique.append(r)
    return unique


def _visible_text_blob(structure: dict[str, Any]) -> str:
    chunks: list[str] = [str(structure.get("page_title") or "")]
    for h in structure.get("headings") or []:
        chunks.append(str((h or {}).get("text") or ""))
    for b in structure.get("buttons") or []:
        chunks.append(str((b or {}).get("text") or ""))
    for link in structure.get("links") or []:
        chunks.append(str((link or {}).get("text") or ""))
    return " ".join(chunks)


def _redact_observation(
    obs: dict[str, Any],
    *,
    include_structure: bool = False,
    login_completed_hint: bool | None = None,
    login_completion_reason: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "title": obs.get("title", ""),
        "current_url": obs.get("current_url", ""),
        "login_required_hint": bool(obs.get("login_required_hint", False)),
        "login_reason": list(obs.get("login_reason") or []),
    }
    if login_completed_hint is not None:
        out["login_completed_hint"] = bool(login_completed_hint)
    if login_completion_reason is not None:
        out["login_completion_reason"] = list(login_completion_reason)
    if include_structure:
        out["page_structure"] = obs.get("page_structure") or {}
    return out


def _err(*, url: str, error_code: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "manual_login_probe",
        "url": url,
        "error_code": error_code,
        "summary": reason[:300],
        "reason": reason[:200],
    }


def _clip_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:200])
        if len(out) >= 50:
            break
    return out


def _normalize_allowed_hosts(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower()[:253])
    return out


def _host_allowed(host: str, allowed: list[str]) -> bool:
    if not allowed:
        return False
    h = (host or "").lower()
    for a in allowed:
        if not a:
            continue
        if h == a:
            return True
        if h.endswith("." + a):
            return True
    return False


__all__ = [
    "probe_manual_login_flow",
]
