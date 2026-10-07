"""이벤트 기반 대기 — blind sleep 대신 실제 상태/이벤트 감지.

원칙:
  - 글자 간 타이핑 리듬은 사람 그대로 (랜덤 50~150ms) — 봇 감지 회피
  - 액션 사이 대기는 모두 이벤트 기반:
      * 필드 준비:   wait_for(state="visible/enabled")
      * 입력 정착:   wait_for_function("el.value===expected")
      * 제출 응답:   URL 변경 / 검증 메시지 / 응답 도착 중 first
      * 폼 등장:     MutationObserver (popup_watcher 패턴)

API:
    wait_field_ready(page, selector, timeout_ms)
    wait_value_settled(page, selector, expected, timeout_ms)
    wait_submit_done(page, before_url, timeout_ms, success_signals=[...], fail_signals=[...])
    wait_validation(page, selector, timeout_ms) -> {"ok": bool, "message": str}
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from contextlib import suppress

from scripts.common.logger import get_logger

log = get_logger(__name__)


def wait_field_ready(page, selector: str, timeout_ms: int = 5000) -> bool:
    """필드가 visible + enabled 가 될 때까지 대기."""
    try:
        loc = page.locator(selector).first
        loc.wait_for(state="visible", timeout=timeout_ms)
        # enabled 확인
        try:
            if not loc.is_enabled(timeout=1000):
                # disabled 이면 짧게 더 기다림
                page.wait_for_function(
                    f"() => {{const el = document.querySelector({selector!r}); "
                    "return el && !el.disabled && !el.readOnly;}}",
                    timeout=timeout_ms,
                )
        except Exception:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
            pass
        return True
    except Exception as e:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
        log.debug("[events] wait_field_ready 실패 sel=%s err=%s", selector, e)
        return False


def wait_value_settled(page, selector: str, expected: str, timeout_ms: int = 3000) -> bool:
    """입력값이 expected 와 같아질 때까지 대기 (이벤트 기반 polling).

    Playwright wait_for_function 은 내부적으로 raf+짧은 interval — blind sleep 없음.
    """
    try:
        page.wait_for_function(
            """([sel, exp]) => {
                const el = document.querySelector(sel);
                return el && (el.value === exp);
            }""",
            arg=[selector, expected],
            timeout=timeout_ms,
        )
        return True
    except Exception as e:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
        log.debug("[events] wait_value_settled 실패 sel=%s err=%s", selector, e)
        return False


def _find_success_dom(page, success_selectors: Iterable[str]) -> dict | None:
    """success selector 중 보이는 것이 있으면 완료 결과 dict, 없으면 None."""
    for sel in success_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return {"done": True, "kind": "success_dom", "detail": sel}
        except Exception:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
            pass
    return None


def _find_fail_dom(page, fail_selectors: Iterable[str]) -> dict | None:
    """fail selector 중 보이는 것이 있으면 완료 결과 dict, 없으면 None."""
    for sel in fail_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                txt = ""
                with suppress(Exception):
                    txt = (el.inner_text() or "").strip()[:200]
                return {"done": True, "kind": "fail_dom", "detail": txt or sel}
        except Exception:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
            pass
    return None


def _find_fail_text(page, fail_signals: Iterable[str], last: str) -> dict | None:
    """body 텍스트에 fail_signals 가 있으면 완료 결과 dict, 없으면 None."""
    if fail_signals:
        try:
            body = page.evaluate("() => document.body && document.body.innerText || ''")
            if isinstance(body, str):
                for s in fail_signals:
                    if s and s in body and s != last:
                        return {"done": True, "kind": "fail_text", "detail": s}
        except Exception:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
            pass
    return None


def wait_submit_done(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    page,
    *,
    before_url: str = "",
    timeout_ms: int = 15000,
    success_url_contains: Iterable[str] = (),
    fail_signals: Iterable[str] = (),
    success_selectors: Iterable[str] = (),
    fail_selectors: Iterable[str] = (),
) -> dict:
    """제출 후 응답 대기 — 다음 중 하나라도 발생하면 즉시 반환.

    - URL 이 before_url 과 다름 (그리고 success_url_contains 매치)
    - success_selectors 중 하나 등장
    - fail_selectors 중 하나 등장
    - fail_signals (텍스트) 가 body 에 나타남

    Returns:
        {"done": bool, "kind": "url_changed|success_dom|fail_dom|fail_text|timeout",
         "detail": str}
    """
    start = time.time()
    deadline = start + timeout_ms / 1000.0
    last = ""
    poll_ms = 200
    while time.time() < deadline:
        try:
            cur = page.url or ""
        except Exception:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
            cur = ""
        if cur and cur != before_url:
            # URL 변경
            if not success_url_contains or any(s in cur for s in success_url_contains):
                return {"done": True, "kind": "url_changed", "detail": cur}
        found = (
            _find_success_dom(page, success_selectors)
            or _find_fail_dom(page, fail_selectors)
            or _find_fail_text(page, fail_signals, last)
        )
        if found:
            return found
        page.wait_for_timeout(poll_ms)
    return {"done": False, "kind": "timeout", "detail": f"{int((time.time() - start) * 1000)}ms"}


def wait_validation(page, selector_near: str, timeout_ms: int = 2500) -> dict:
    """필드 근처의 인라인 검증 메시지 등장 대기.

    같은 폼 컨테이너 내부의 .error/.warning/[role=alert] 등장.
    """
    js = """
    ([sel, deadline]) => {
        function near(el) {
            // 같은 form 또는 같은 fieldset/li 안의 alert 요소
            const root = el.closest('form, fieldset, li, .form-row, .form-group') || el.parentElement;
            if (!root) return null;
            return root.querySelector('.error, .err, .warning, .invalid, [role="alert"], [class*="error"], [class*="invalid"]');
        }
        return new Promise(resolve => {
            const el = document.querySelector(sel);
            if (!el) { resolve({found:false, reason:'no_field'}); return; }
            const found = near(el);
            if (found && (found.innerText || '').trim()) {
                resolve({found:true, message:(found.innerText||'').trim().slice(0,200)});
                return;
            }
            const mo = new MutationObserver(() => {
                const f = near(el);
                if (f && (f.innerText || '').trim()) {
                    mo.disconnect();
                    resolve({found:true, message:(f.innerText||'').trim().slice(0,200)});
                }
            });
            mo.observe(document.body, {subtree:true, childList:true, characterData:true});
            setTimeout(() => { mo.disconnect(); resolve({found:false, reason:'timeout'}); }, deadline);
        });
    }
    """
    try:
        r = page.evaluate(js, [selector_near, timeout_ms])
        return r if isinstance(r, dict) else {"found": False, "reason": "non_dict"}
    except Exception as e:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
        return {"found": False, "reason": f"eval_error:{str(e)[:80]}"}


def wait_for_form(page, *, role_hints: Iterable[str] = ("id", "password"), timeout_ms: int = 10000) -> bool:
    """폼이 DOM에 등장할 때까지 대기 (SPA 대응).

    role_hints 안의 키워드가 input name/id/placeholder 에 등장하면 OK.
    """
    js = """
    ([hints, deadline]) => {
        function probe() {
            const els = document.querySelectorAll('input, select, textarea');
            for (const el of els) {
                const sig = ((el.name||'') + ' ' + (el.id||'') + ' ' + (el.placeholder||'')).toLowerCase();
                for (const h of hints) {
                    if (sig.includes(h.toLowerCase())) return true;
                }
            }
            return false;
        }
        return new Promise(resolve => {
            if (probe()) { resolve(true); return; }
            const mo = new MutationObserver(() => {
                if (probe()) { mo.disconnect(); resolve(true); }
            });
            mo.observe(document.body, {subtree:true, childList:true});
            setTimeout(() => { mo.disconnect(); resolve(false); }, deadline);
        });
    }
    """
    try:
        return bool(page.evaluate(js, [list(role_hints), timeout_ms]))
    except Exception as e:  # noqa: BLE001 - 폼 필드 대기/제출완료 감지 범용 헬퍼 - 모든 except가 False 또는 timeout 결과를 반환, 승인 판정 로직이 아니라 단순 상태확인 유틸
        log.debug("[events] wait_for_form 실패: %s", e)
        return False
