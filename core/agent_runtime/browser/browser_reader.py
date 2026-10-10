"""local_agent read-only browser page reader (Stage 2).

실제 브라우저 엔진(Playwright Chromium)을 read-only 모드로 열어 URL 에 접속하고,
현재 페이지의 title / current_url / HTML 을 수집한 뒤
``web_reader.analyze_html_structure`` 로 구조화해 반환한다.

본 모듈은 Stage 2 의 범위 안에서 다음 작업을 절대 수행하지 않는다.

  - 마우스/키보드 조작 API 호출 (모든 입력·클릭·키 입력 API 금지)
  - 폼 전송, 파일 저장, 다운로드 이벤트 처리, 업로드
  - 쿠키 / 세션 스토리지 / 브라우저 세션 상태 수집
  - password / hidden input value 저장 (web_reader 가 이미 드롭)
  - POST 요청 명시적 전송
  - screenshot 저장 (Stage 3 에 이미 존재 — 이 모듈에선 다루지 않음)

반환 dict 는 HTML 원문 전체를 포함하지 않으며, 전달되는 HTML 역시
``web_reader.analyze_html_structure`` 가 민감 토큰을 드롭한 후 구조 요약만
``page_structure`` 필드로 담는다.

테스트 편의를 위해 ``_playwright_factory`` 인자로 가짜 팩토리를 주입할 수
있다. None 이면 실제 ``playwright.sync_api.sync_playwright`` 를 사용하며
Playwright 가 설치되어 있지 않은 환경에서는
``error_code="BROWSER_DEPENDENCY_MISSING"`` 로 즉시 실패를 반환한다.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable
from urllib.parse import urlparse

from core.agent_runtime.browser.web_reader import analyze_html_structure, validate_url_for_readonly_open
from core.agent_runtime.common import audit as _audit
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed

logger = logging.getLogger(__name__)


class BrowserDependencyMissing(RuntimeError):
    """Playwright 또는 브라우저 엔진이 설치되지 않음."""


# ── 로그인/모달 추정에 사용하는 키워드 표 ────────────────────────────────

_LOGIN_KEYWORDS: tuple[str, ...] = (
    "로그인", "아이디", "비밀번호",
    "Sign in", "Login", "account", "password",
    "인증", "2단계 인증", "OTP",
)

_MODAL_CLASS_TOKENS: tuple[str, ...] = ("modal", "popup", "layer", "dialog")
_MODAL_CLOSE_BUTTON_TEXTS: tuple[str, ...] = (
    "닫기", "확인", "취소", "close", "ok",
)

# 허용된 wait_until 값 (Playwright 공식 옵션 화이트리스트).
_ALLOWED_WAIT_UNTIL: frozenset[str] = frozenset({
    "domcontentloaded", "load", "networkidle", "commit",
})


# ── 공개 API ─────────────────────────────────────────────────────────────

def open_url_readonly(  # noqa: PLR0913 - 공개 API keyword-only 시그니처 유지(호출부·테스트 다수)
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 15000,
    max_html_chars: int = 500000,
    keyword_hints: list[str] | None = None,
    allow_private_network: bool = False,
    allow_about_blank: bool = False,
    headless: bool | None = None,
    keep_open_ms: int = 0,
    browser_channel: str = "",
    _playwright_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """URL 을 read-only 로 열고 페이지 구조 요약 dict 를 반환.

    어떤 경우에도 클릭/입력/제출/다운로드/쿠키 수집을 수행하지 않는다.
    결과 dict 에 HTML 원문 전체는 포함되지 않으며,
    ``page_structure`` 에는 ``web_reader.analyze_html_structure`` 가 이미
    민감 토큰을 드롭한 요약만 담긴다.

    ``allow_about_blank=True`` 일 때만 정확히 ``about:blank`` 문자열이
    URL 검증을 통과한다. Stage 12I controlled observe 첫 후보용 게이트이며,
    호출자가 명시하지 않으면 기본 동작(URL_SCHEME_BLOCKED)이 유지된다.
    """
    url_category = _categorize_url(url)
    if headless is None:
        headless = os.getenv("HAEHAN_BROWSER_HEADLESS", "true").lower() != "false"
    try:
        keep_open_ms = int(keep_open_ms)
    except (TypeError, ValueError):
        keep_open_ms = 0
    keep_open_ms = max(0, min(keep_open_ms, 30000))
    browser_channel = _normalize_browser_channel(browser_channel)

    audit_base = _build_audit_base(
        url_category, allow_about_blank, allow_private_network, headless, keep_open_ms, browser_channel,
    )

    _audit.log_local_event("browser_open_requested", **audit_base)

    validation = validate_url_for_readonly_open(
        url,
        allow_private_network=allow_private_network,
        allow_about_blank=allow_about_blank,
    )
    _audit.log_local_event(
        "browser_open_dry_run_checked",
        validation_ok=bool(validation.get("ok")),
        **audit_base,
    )
    if not validation.get("ok"):
        ec = validation.get("error_code", "URL_INVALID")
        _audit.log_local_event(
            "browser_open_blocked", error_code=ec, **audit_base,
        )
        return _err(
            url=url,
            error_code=ec,
            reason=validation.get("reason", "url validation failed"),
        )

    if wait_until not in _ALLOWED_WAIT_UNTIL:
        wait_until = "domcontentloaded"
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        timeout_ms = 15000
    if not isinstance(max_html_chars, int) or max_html_chars <= 0:
        max_html_chars = 500000

    factory, dep_err = _resolve_playwright_factory(_playwright_factory, url, audit_base)
    if dep_err is not None:
        return dep_err
    assert factory is not None  # _resolve_playwright_factory 계약: dep_err 가 None 이면 항상 factory(동작 변경 없음, mypy 용 타입 좁히기)

    _audit.log_local_event("browser_open_started", **audit_base)

    try:
        page_title, current_url, html = _open_and_read(
            factory, url,
            wait_until=wait_until,
            timeout_ms=timeout_ms,
            headless=bool(headless),
            keep_open_ms=keep_open_ms,
            browser_channel=browser_channel,
        )
    except BrowserDependencyMissing as e:
        _audit.log_local_event(
            "browser_open_failed",
            error_code="BROWSER_DEPENDENCY_MISSING",
            **audit_base,
        )
        return _err(
            url=url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            reason=str(e)[:200],
        )
    except Exception as e:  # pragma: no cover - 실제 환경 오류
        logger.exception("browser open failed")
        _audit.log_local_event(
            "browser_open_failed",
            error_code="BROWSER_OPEN_FAILED",
            **audit_base,
        )
        return _err(
            url=url,
            error_code="BROWSER_OPEN_FAILED",
            reason=str(e)[:200],
        )

    html, html_truncated = _truncate_html(html, max_html_chars)

    page_structure = analyze_html_structure(
        html=html, base_url=current_url, keyword_hints=keyword_hints,
    )

    login_hint, login_reason = _detect_login_required(page_structure)
    modal_candidates = _detect_modal_candidates(html)

    summary = _page_summary(page_title, page_structure)
    _log_observed(audit_base, page_title, login_hint, modal_candidates, html_truncated)

    return {
        "ok": True,
        "url": url,
        "url_category": url_category,
        "current_url": (current_url or "")[:500],
        "title": (page_title or "")[:300],
        "html_truncated": html_truncated,
        "headless": bool(headless),
        "keep_open_ms": keep_open_ms,
        "browser_channel": browser_channel or "chromium",
        "login_required_hint": login_hint,
        "login_reason": login_reason,
        "modal_candidates": modal_candidates,
        "page_structure": page_structure,
        "summary": summary,
    }


def _build_audit_base(
    url_category: str,
    allow_about_blank: bool,
    allow_private_network: bool,
    headless: bool | None,
    keep_open_ms: int,
    browser_channel: str,
) -> dict[str, Any]:
    audit_base = {
        "action": "controlled_browser_open",
        "url_category": url_category,
        "allow_about_blank": bool(allow_about_blank),
        "allow_private_network": bool(allow_private_network),
        "headless": bool(headless),
        "keep_open_ms": keep_open_ms,
        "browser_channel": browser_channel or "chromium",
        "dry_run": False,
    }
    # url 원문은 about:blank 인 경우에만 audit 에 포함
    if url_category == "about_blank":
        audit_base["url"] = "about:blank"
    return audit_base


def _resolve_playwright_factory(
    factory: Callable[[], Any] | None,
    url: str,
    audit_base: dict[str, Any],
) -> tuple[Callable[[], Any] | None, dict[str, Any] | None]:
    """주입된 factory 가 없으면 playwright 를 로드. (factory, 오류결과)."""
    if factory is None:
        assert_browser_launch_allowed(component="core.agent_runtime.browser.browser_reader", action="playwright_launch")
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright
        except ImportError:
            _audit.log_local_event(
                "browser_open_failed",
                error_code="BROWSER_DEPENDENCY_MISSING",
                **audit_base,
            )
            return None, _err(
                url=url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                reason="playwright not installed: pip install playwright",
            )
        factory = _sync_playwright
    return factory, None


def _truncate_html(html: Any, max_html_chars: int) -> tuple[str, bool]:
    html_truncated = False
    if not isinstance(html, str):
        html = ""
    if len(html) > max_html_chars:
        html = html[:max_html_chars]
        html_truncated = True
    return html, html_truncated


def _page_summary(page_title: Any, page_structure: dict[str, Any]) -> str:
    counts = page_structure.get("counts", {}) or {}
    return (
        f"title={(page_title or '')[:60]} "
        f"links={counts.get('links', 0)} "
        f"buttons={counts.get('buttons', 0)} "
        f"forms={counts.get('forms', 0)} "
        f"tables={counts.get('tables', 0)}"
    )


def _log_observed(
    audit_base: dict[str, Any],
    page_title: Any,
    login_hint: bool,
    modal_candidates: list[dict[str, Any]],
    html_truncated: bool,
) -> None:
    # 관찰 결과 audit — title/url 본문은 기록하지 않고 카운트와 힌트만 남긴다
    _audit.log_local_event(
        "browser_open_observed",
        pages_observed_count=1,
        title_len=len((page_title or "")),
        login_required_hint=bool(login_hint),
        modal_candidates_count=len(modal_candidates or []),
        html_truncated=bool(html_truncated),
        **audit_base,
    )
    _audit.log_local_event(
        "browser_open_completed",
        status_category="ok",
        **audit_base,
    )


def _categorize_url(url: Any) -> str:
    """audit 용 URL 카테고리 분류. 외부 호스트명을 audit 에 노출하지 않기 위함."""
    if not isinstance(url, str):
        return "invalid"
    raw = url.strip().lower()
    if not raw:
        return "empty"
    if raw == "about:blank":
        return "about_blank"
    if raw.startswith("about:"):
        return "about_other"
    try:
        scheme = (urlparse(raw).scheme or "").lower()
    except ValueError:
        return "parse_failed"
    if scheme in ("http", "https"):
        return f"public_{scheme}"
    if not scheme:
        return "no_scheme"
    return f"blocked_scheme:{scheme}"


# ── 내부 ────────────────────────────────────────────────────────────────

def _err(*, url: str, error_code: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "url": url,
        "error_code": error_code,
        "reason": reason[:200],
    }


def _normalize_browser_channel(value: Any) -> str:
    channel = str(value or "").strip().lower()
    if channel in {"", "chromium"}:
        return ""
    if channel in {"chrome", "msedge"}:
        return channel
    return ""


def _open_and_read(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 1곳
    factory: Callable[[], Any],
    url: str,
    *,
    wait_until: str,
    timeout_ms: int,
    headless: bool,
    keep_open_ms: int,
    browser_channel: str,
) -> tuple[str, str, str]:
    """브라우저를 띄워 title/current_url/html 만 수집 후 전원 종료.

    finally 체인으로 page/context/browser 를 항상 close 한다. 어떤 종류의
    마우스/키보드 조작 API 도 호출하지 않는다.
    """
    with factory() as pw:
        launch_kwargs: dict[str, Any] = {"headless": headless}
        if browser_channel:
            launch_kwargs["channel"] = browser_channel
        browser = pw.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    page_title = page.title()
                    current_url = page.url
                    html = page.content()
                    if keep_open_ms > 0:
                        time.sleep(keep_open_ms / 1000.0)
                    return page_title, current_url, html
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _safe_close(obj: Any) -> None:
    try:
        closer = getattr(obj, "close", None)
        if callable(closer):
            closer()
    except Exception:
        logger.debug("close failed", exc_info=True)


def _detect_login_required(
    page_structure: dict[str, Any],
) -> tuple[bool, list[str]]:
    """HTML 구조에서 로그인 페이지 가능성 추정.

    - password 타입 input 존재 → "password_input_detected"
    - 로그인/인증 관련 키워드 발견 → "login_keyword"
    비밀번호 값 자체는 절대 수집하지 않는다.
    """
    reasons: list[str] = []
    inputs = page_structure.get("inputs") or []
    has_password = any(
        isinstance(i, dict) and i.get("type") == "password" for i in inputs
    )
    if has_password:
        reasons.append("password_input_detected")

    chunks: list[str] = [str(page_structure.get("page_title") or "")]
    for h in page_structure.get("headings") or []:
        chunks.append(str((h or {}).get("text") or ""))
    for b in page_structure.get("buttons") or []:
        chunks.append(str((b or {}).get("text") or ""))
    for link in page_structure.get("links") or []:
        chunks.append(str((link or {}).get("text") or ""))
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        chunks.append(str(inp.get("placeholder") or ""))
        chunks.append(str(inp.get("label") or ""))

    blob = " ".join(chunks)
    blob_lower = blob.lower()
    for kw in _LOGIN_KEYWORDS:
        if kw in blob or kw.lower() in blob_lower:
            reasons.append("login_keyword")
            break

    return (len(reasons) > 0, reasons)


def _iter_modal_hits(html: str):
    """모달 후보 (text, reason) 을 원래 탐색 순서대로 산출."""
    for _m in re.finditer(r'role\s*=\s*["\']dialog["\']', html, re.IGNORECASE):
        yield "", "role_dialog"

    for token in _MODAL_CLASS_TOKENS:
        pattern = rf'(?:class|id)\s*=\s*["\'][^"\']*{re.escape(token)}[^"\']*["\']'
        for _m in re.finditer(pattern, html, re.IGNORECASE):
            yield "", f"class_or_id:{token}"

    for txt in _MODAL_CLOSE_BUTTON_TEXTS:
        pattern = rf'<button[^>]*>\s*{re.escape(txt)}\s*</button>'
        for _m in re.finditer(pattern, html, re.IGNORECASE):
            yield txt, f"close_button:{txt}"


def _detect_modal_candidates(html: str) -> list[dict[str, Any]]:
    """HTML 에서 팝업/모달 후보만 구조적으로 추정. 닫기 동작은 수행하지 않는다."""
    if not isinstance(html, str) or not html:
        return []

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    limit_per_reason: dict[str, int] = {}
    MAX_PER_REASON = 5
    MAX_TOTAL = 30

    def _add(text: str, reason: str) -> None:
        if len(candidates) >= MAX_TOTAL:
            return
        if limit_per_reason.get(reason, 0) >= MAX_PER_REASON:
            return
        key = (text[:80], reason)
        if key in seen:
            return
        seen.add(key)
        limit_per_reason[reason] = limit_per_reason.get(reason, 0) + 1
        candidates.append({"text": text[:80], "reason": reason})

    for text, reason in _iter_modal_hits(html):
        _add(text, reason)

    return candidates


__all__ = [
    "BrowserDependencyMissing",
    "open_url_readonly",
]
