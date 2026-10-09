"""local_agent guarded browser actions (Stage 3 골격).

이 모듈은 웹 페이지에서의 클릭/입력/선택/스크롤 액션을
read/write 경계 기준으로 검증한 뒤 **low/medium 안전 액션만**
실제 브라우저에서 실행한다. high/critical 로 분류된 액션은 절대
실제 브라우저 API 를 호출하지 않고 ``approval_required=True`` 로
반환한다.

본 모듈이 **절대** 수행하지 않는 것 (이번 단계 금지):

  - form 전송 (submit_form), 파일 업로드 (set_input_files)
  - 파일 다운로드 이벤트 처리
  - 쿠키 / storage_state / session 상태 수집
  - password 입력 필드에 대한 값 입력
  - 삭제/승인/결제/확정/마감/로그아웃 버튼 클릭
  - 계정/토큰/비밀번호 값의 로그 기록 또는 반환

테스트 편의를 위해 ``_playwright_factory`` 로 가짜 팩토리를 주입할 수
있다. Playwright 가 설치되어 있지 않으면
``BROWSER_DEPENDENCY_MISSING`` 으로 즉시 실패한다.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from core.agent_runtime.browser.web_reader import MEDIUM_KEYWORDS, RISK_WRITE_KEYWORDS, validate_url_for_readonly_open
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed

logger = logging.getLogger(__name__)


# ── 정책 테이블 ──────────────────────────────────────────────────────────

# 항상 blocked — 실제 실행 코드에서 분기조차 만들지 않는다.
_BLOCKED_ACTIONS: frozenset[str] = frozenset({
    "submit_form", "form_submit",
    "upload_file", "upload",
    "download_file", "download",
    "delete", "delete_account",
    "approve", "payment",
    "credential_submit", "password_fill",
    "storage_state", "cookies", "add_cookies",
    "set_input_files",
})

# 본 단계에서 분기/실행을 허용하는 상위 레벨 액션명.
_ALLOWED_ACTIONS: frozenset[str] = frozenset({
    "click",
    "type_text", "fill",
    "select_option",
    "scroll",
    "read_navigation",
})

# critical 로 즉시 상향하는 파괴적 키워드 (텍스트/셀렉터 공통).
_CRITICAL_TEXT_TOKENS: tuple[str, ...] = (
    "삭제", "탈퇴", "결제", "승인", "확정", "마감", "로그아웃",
    "delete", "remove", "destroy", "logout", "signout", "payment",
)

# password 관련 셀렉터/네임 힌트.
_PASSWORD_HINT_RE = re.compile(
    r"(password|passwd|\bpwd\b|type\s*=\s*['\"]?password['\"]?)",
    re.IGNORECASE,
)

# Playwright 공식 wait_until 값 화이트리스트.
_ALLOWED_WAIT_UNTIL: frozenset[str] = frozenset({
    "domcontentloaded", "load", "networkidle", "commit",
})

# 스크롤 1회당 최대 허용 이동 거리 (px).
_MAX_SCROLL_DELTA: int = 10000


# ── 예외 ──────────────────────────────────────────────────────────────────

class BrowserActionBlocked(Exception):
    """액션이 정책상 절대 허용되지 않음."""


class ApprovalRequired(Exception):
    """액션은 승인이 필요하며 본 함수는 실행하지 않았음."""


class BrowserActionDependencyMissing(RuntimeError):
    """Playwright 또는 브라우저 엔진이 설치되지 않음."""


@dataclass
class BrowserActionRequest:
    action: str
    selector: str | None = None
    text: str | None = None
    value: str | None = None
    risk_hint: str | None = None


# ── 위험도 분류 ──────────────────────────────────────────────────────────

def classify_browser_action(
    action: str,
    selector: str | None = None,
    text: str | None = None,
    value: str | None = None,
) -> dict[str, Any]:
    """action/selector/text 를 보고 위험도·카테고리·승인 필요 여부를 반환.

    반환 키:
      - ``risk``: "low" | "medium" | "high" | "critical"
      - ``category``: "safe_read" | "safe_input" | "danger_write" | "blocked"
      - ``requires_approval``: bool
      - ``reason``: 분류 사유 토큰 리스트
    """
    action_lc = (action or "").strip().lower()
    text_str = (text or "").strip()
    selector_str = (selector or "").strip()
    reasons: list[str] = []

    # 1) 항상 blocked 인 액션명은 분기도 하지 않는다.
    if action_lc in _BLOCKED_ACTIONS:
        reasons.append(f"blocked_action:{action_lc}")
        return _result("critical", "blocked", True, reasons)

    if action_lc not in _ALLOWED_ACTIONS:
        reasons.append(f"unknown_action:{action_lc or '(empty)'}")
        return _result("critical", "blocked", True, reasons)

    # 2) password 힌트가 있으면 type/fill 뿐 아니라 click 에도 블록.
    if _PASSWORD_HINT_RE.search(selector_str) or _PASSWORD_HINT_RE.search(text_str):
        reasons.append("selector_hint:password")
        return _result("high", "blocked", True, reasons)

    if action_lc == "scroll":
        reasons.append("scroll:low")
        return _result("low", "safe_read", False, reasons)

    if action_lc == "read_navigation":
        reasons.append("read_navigation:low")
        return _result("low", "safe_read", False, reasons)

    if action_lc in ("type_text", "fill"):
        # 일반 입력 필드는 medium / safe_input. password 는 위에서 이미 걸렀다.
        reasons.append(f"{action_lc}:medium")
        return _result("medium", "safe_input", False, reasons)

    if action_lc == "select_option":
        reasons.append("select_option:medium")
        return _result("medium", "safe_input", False, reasons)

    if action_lc == "click":
        return _classify_click(text_str, selector_str, reasons)

    # 방어적 fallback — 정의되지 않은 경로.
    reasons.append(f"unhandled:{action_lc}")
    return _result("critical", "blocked", True, reasons)


def _classify_click(
    text: str,
    selector: str,
    reasons: list[str],
) -> dict[str, Any]:
    lowered_all = f"{text} {selector}".lower()

    # 2-a) 파괴적 토큰 (삭제/결제/승인/확정/마감/탈퇴/로그아웃 등) → critical.
    for token in _CRITICAL_TEXT_TOKENS:
        if token in text or token.lower() in lowered_all:
            reasons.append(f"keyword:{token}")
            return _result("critical", "danger_write", True, reasons)

    # 2-b) 쓰기성 키워드 (저장/제출/등록/수정/전송/신청/취소) → high.
    for token in RISK_WRITE_KEYWORDS:
        if token in text or token in selector:
            # 위의 critical 과 중복되지 않은 항목만 여기 도달.
            reasons.append(f"keyword:{token}")
            return _result("high", "danger_write", True, reasons)

    # 2-c) 다운로드/export 류 → medium danger_write (이번 단계 미구현, approval).
    for token in MEDIUM_KEYWORDS:
        if token.lower() in lowered_all:
            reasons.append(f"keyword:{token}")
            return _result("medium", "danger_write", True, reasons)

    # 2-d) submit 타입 셀렉터 힌트 → high.
    if re.search(r"type\s*=\s*['\"]?submit['\"]?", selector, re.IGNORECASE):
        reasons.append("selector_hint:submit")
        return _result("high", "danger_write", True, reasons)

    # 2-e) 기본값: 안전한 링크/버튼 클릭.
    reasons.append("click:safe")
    return _result("low", "safe_read", False, reasons)


def _result(
    risk: str, category: str, requires_approval: bool, reasons: list[str],
) -> dict[str, Any]:
    return {
        "risk": risk,
        "category": category,
        "requires_approval": bool(requires_approval),
        "reason": list(reasons),
    }


# ── 실제 실행 게이트 ──────────────────────────────────────────────────────

def perform_browser_action_readwrite_guarded(  # noqa: PLR0913 - 공개 API 시그니처 유지(호출부 다수)
    url: str,
    action: str,
    *,
    selector: str | None = None,
    text: str | None = None,
    value: str | None = None,
    timeout_ms: int = 15000,
    allow_private_network: bool = False,
    approved: bool = False,
    wait_until: str = "domcontentloaded",
    _playwright_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """URL 을 열고 low/medium 안전 액션만 실제로 수행.

    high/critical 은 절대 브라우저 API 를 호출하지 않고
    ``approval_required=True, action_executed=False`` 로 반환한다.
    blocked 액션도 동일하게 즉시 거절된다.
    """
    # 1) URL 안전성.
    validation = validate_url_for_readonly_open(
        url, allow_private_network=allow_private_network,
    )
    if not validation.get("ok"):
        return _error_result(
            url=url,
            error_code=validation.get("error_code", "URL_INVALID"),
            reason=validation.get("reason", "url validation failed"),
            classification=None,
        )

    # 2) 위험도 분류.
    classification = classify_browser_action(
        action=action, selector=selector, text=text, value=value,
    )
    risk = classification["risk"]
    category = classification["category"]

    # 3) blocked 은 즉시 거절. 절대 브라우저 API 미호출.
    if category == "blocked":
        return _guarded_result(
            ok=True, url=url, action=action,
            classification=classification,
            approval_required=True,
            action_executed=False,
            summary=f"blocked:{action} risk={risk}",
        )

    # 4) high/critical 은 approved 무관하게 이번 단계에서 실행 금지.
    if risk in ("high", "critical"):
        return _guarded_result(
            ok=True, url=url, action=action,
            classification=classification,
            approval_required=True,
            action_executed=False,
            summary=f"approval_required:{action} risk={risk}",
        )

    # 5) low/medium — 실제 실행.
    if wait_until not in _ALLOWED_WAIT_UNTIL:
        wait_until = "domcontentloaded"
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        timeout_ms = 15000

    factory = _playwright_factory
    if factory is None:
        assert_browser_launch_allowed(component="core.agent_runtime.browser.browser_actions", action="playwright_launch")
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright
        except ImportError:
            return _error_result(
                url=url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                reason="playwright not installed: pip install playwright",
                classification=classification,
            )
        factory = _sync_playwright

    try:
        exec_trace = _run_safe_action(
            factory, url,
            action=(action or "").strip().lower(),
            selector=selector, text=text, value=value,
            wait_until=wait_until, timeout_ms=timeout_ms,
        )
    except BrowserActionDependencyMissing as e:
        return _error_result(
            url=url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            reason=str(e)[:200],
            classification=classification,
        )
    except Exception as e:  # pragma: no cover - 환경별 실패
        logger.exception("browser action failed")
        return _error_result(
            url=url,
            error_code="BROWSER_ACTION_FAILED",
            reason=str(e)[:200],
            classification=classification,
        )

    return _guarded_result(
        ok=True, url=url, action=action,
        classification=classification,
        approval_required=False,
        action_executed=True,
        summary=f"ok:{action} risk={risk}",
        exec_trace=exec_trace,
    )


# ── 내부: 실제 Playwright 조작 ───────────────────────────────────────────

def _run_safe_action(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 1곳
    factory: Callable[[], Any],
    url: str,
    *,
    action: str,
    selector: str | None,
    text: str | None,
    value: str | None,
    wait_until: str,
    timeout_ms: int,
) -> list[str]:
    """low/medium 으로 분류된 action 만 실행한다.

    어떤 경우에도 form submit/파일 업로드/다운로드/쿠키 조작 API 를
    호출하지 않는다. finally 체인으로 page/context/browser 를 모두 close.
    """
    trace: list[str] = []
    with factory() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                    trace.append("goto")
                    _dispatch_safe_action(
                        page, action=action,
                        selector=selector, text=text, value=value,
                        timeout_ms=timeout_ms, trace=trace,
                    )
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)
    return trace


def _dispatch_safe_action(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 1곳
    page: Any,
    *,
    action: str,
    selector: str | None,
    text: str | None,
    value: str | None,
    timeout_ms: int,
    trace: list[str],
) -> None:
    if action == "click":
        target = selector if selector else (f"text={text}" if text else "")
        if not target:
            raise RuntimeError("click requires selector or text")
        page.click(target, timeout=timeout_ms)
        trace.append("click")
        return

    if action in ("type_text", "fill"):
        if not selector:
            raise RuntimeError("type_text requires selector")
        page.fill(selector, value if value is not None else (text or ""),
                  timeout=timeout_ms)
        trace.append("fill")
        return

    if action == "select_option":
        if not selector:
            raise RuntimeError("select_option requires selector")
        page.select_option(selector, value, timeout=timeout_ms)
        trace.append("select_option")
        return

    if action == "scroll":
        delta_y = _scroll_delta(value)
        page.mouse.wheel(0, delta_y)
        trace.append("scroll")
        return

    if action == "read_navigation":
        _ = page.title()
        trace.append("read_navigation")
        return

    raise RuntimeError(f"unhandled safe action: {action!r}")


def _scroll_delta(value: str | None) -> int:
    delta_y = 500
    try:
        if value is not None:
            delta_y = int(value)
    except (TypeError, ValueError):
        delta_y = 500
    if delta_y > _MAX_SCROLL_DELTA:
        delta_y = _MAX_SCROLL_DELTA
    if delta_y < -_MAX_SCROLL_DELTA:
        delta_y = -_MAX_SCROLL_DELTA
    return delta_y


def _safe_close(obj: Any) -> None:
    try:
        closer = getattr(obj, "close", None)
        if callable(closer):
            closer()
    except Exception:
        logger.debug("close failed", exc_info=True)


# ── 결과 포맷 ────────────────────────────────────────────────────────────

def _guarded_result(  # noqa: PLR0913 - keyword-only 결과 포맷터, 공개 응답 key 유지
    *,
    ok: bool,
    url: str,
    action: str,
    classification: dict[str, Any],
    approval_required: bool,
    action_executed: bool,
    summary: str,
    exec_trace: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": bool(ok),
        "url": url,
        "action": action,
        "risk": classification.get("risk", "critical"),
        "category": classification.get("category", "blocked"),
        "classification": dict(classification),
        "approval_required": bool(approval_required),
        "action_executed": bool(action_executed),
        "summary": summary[:300] if isinstance(summary, str) else "",
    }
    if exec_trace is not None:
        out["exec_trace"] = list(exec_trace)
    return out


def _error_result(
    *,
    url: str,
    error_code: str,
    reason: str,
    classification: dict[str, Any] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "url": url,
        "error_code": error_code,
        "reason": (reason or "")[:200],
        "action_executed": False,
    }
    if classification is not None:
        out["classification"] = dict(classification)
        out["risk"] = classification.get("risk", "critical")
        out["category"] = classification.get("category", "blocked")
        out["approval_required"] = bool(classification.get("requires_approval", True))
    else:
        out["approval_required"] = True
        out["risk"] = "critical"
        out["category"] = "blocked"
    return out


def action_browser_inspect(params: dict) -> "BrowserActionRequest | dict[str, Any]":
    """browser.inspect stub (dry_run only).
    
    Args:
        params: dict with optional keys:
          - dry_run: bool (default False)
          - url: str (optional)
    
    Returns:
        dict with dry_run mock response or blocked response.
    """
    from datetime import datetime, timezone
    
    dry_run = params.get("dry_run", False)
    if not isinstance(dry_run, bool):
        dry_run = str(dry_run).lower() in ("true", "1", "yes")

    url = params.get("url")
    if url is not None:
        url = str(url).strip() or None

    now = datetime.now(timezone.utc).isoformat()
    
    if dry_run:
        return {
            "ok": True,
            "action": "browser.inspect",
            "dry_run": True,
            "browser_started": False,
            "url": url,
            "title": "DRY_RUN_BROWSER_INSPECT",
            "status": "ok",
            "timestamp": now,
        }
    else:
        return {
            "ok": False,
            "action": "browser.inspect",
            "dry_run": False,
            "browser_started": False,
            "reason": "actual_browser_execution_not_enabled",
            "timestamp": now,
        }


__all__ = [
    "action_browser_inspect",
    "BrowserActionBlocked",
    "ApprovalRequired",
    "BrowserActionDependencyMissing",
    "BrowserActionRequest",
    "classify_browser_action",
    "perform_browser_action_readwrite_guarded",
]
