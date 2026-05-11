"""웹 자동화 공통 페이지 헬퍼.

모든 웹 접속 스크립트에서 import해서 사용.

기본 패턴:
    page_goto(page, url)                              # 이동
    page_goto_wait(page, url, selector)               # 이동 후 목표 요소 등장 즉시 진행
    page_wait_visible(page, selector)                 # 요소 렌더 확인
    page_wait_click(page, selector)                   # 요소 대기 → 클릭 → 에러 감지
    page_wait_type(page, selector, text)              # 요소 대기 → 입력 → 값 검증
    page_wait_nav(page, url_pattern)                  # URL 전환 확인
    page_click_then_wait(page, click_sel, wait_sel)   # 클릭 → 결과 요소 대기 + 에러 경쟁
    page_check_error(page)                            # 에러 메시지 출현 확인

통합 감시 패턴 (입력 → 서버 반영 → UI 반영 완전 검증):
    page_watch_network(page, url_pattern)             # 컨텍스트: 네트워크 요청 감시 시작
    page_watch_dom(page, selector)                    # 컨텍스트: DOM 변화 감시 시작
    page_poll_until(page, selector, check_fn)         # 조건 충족까지 주기적 폴링
    page_submit_and_verify(page, ...)                 # 통합: 제출 → 네트워크+DOM+폴링 3중 검증
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Generator

from playwright.sync_api import Page, Request, Response
from scripts.logger import get_logger

log = get_logger(__name__)

# 공통 에러 메시지 셀렉터
_ERROR_SELECTORS = (
    '[role="alert"], .error-message, .mat-error, '
    '.cfc-error, [class*="error"]:not([class*="no-error"]), '
    'snack-bar-container, .toast-error'
)


# ── 기본 헬퍼 ─────────────────────────────────────────────────────────

def page_goto(page: Page, url: str, timeout: int = 30000) -> None:
    """이동 → domcontentloaded만 대기."""
    log.debug("goto: %s", url)
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")


def page_goto_wait(page: Page, url: str, selector: str, timeout: int = 20000) -> bool:
    """이동 후 목표 요소 등장 시 즉시 진행."""
    log.debug("goto_wait: %s | %s", url, selector)
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    return page_wait_visible(page, selector, timeout=timeout)


def _find_frame(page: Page, selector: str):
    """메인 프레임 + 모든 하위 frame에서 selector에 맞는 (frame, element) 반환.

    Google Console처럼 콘텐츠가 iframe 안에 있을 때 자동으로 올바른 frame을 찾는다.
    """
    for frame in page.frames:
        try:
            el = frame.query_selector(selector)
            if el and el.is_visible():
                return frame, el
        except Exception:
            pass
    return None, None


def page_wait_visible(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 등장 대기. 메인 프레임 실패 시 iframe 자동 탐색."""
    log.debug("wait_visible: %s", selector)
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        log.debug("visible OK: %s", selector)
        return True
    except Exception:
        pass

    # iframe 탐색 fallback
    frame, el = _find_frame(page, selector)
    if el:
        log.debug("visible OK (iframe): %s", selector)
        return True
    log.warn("visible 타임아웃: %s", selector)
    return False


def page_check_error(page: Page, timeout: int = 1500) -> str | None:
    """에러 요소가 있으면 텍스트 반환, 없으면 None."""
    try:
        el = page.wait_for_selector(_ERROR_SELECTORS, timeout=timeout, state="visible")
        msg = el.inner_text().strip()
        log.warn("에러 감지: %s", msg)
        return msg or "(에러 텍스트 없음)"
    except Exception:
        return None


def page_wait_click(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 대기 → 클릭 → 클릭 직후 에러 감지.

    메인 프레임 실패 시 iframe 탐색 → JS 텍스트 fallback 순으로 시도.
    """
    log.debug("wait_click: %s", selector)
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        el.click()
        log.debug("click OK: %s", selector)
    except Exception:
        # iframe 탐색 fallback
        frame, el = _find_frame(page, selector)
        if el:
            el.click()
            log.debug("click OK (iframe): %s", selector)
        else:
            # JS 텍스트 기반 클릭 fallback
            import re
            texts = re.findall(r'has-text\("([^"]+)"\)', selector)
            if texts:
                # 모든 frame에서 텍스트로 클릭 시도
                clicked = None
                for frame in page.frames:
                    try:
                        clicked = frame.evaluate("""(texts) => {
                            for (const text of texts) {
                                const els = Array.from(document.querySelectorAll(
                                    'button, a, [role="button"], span, div'
                                ));
                                const el = els.find(e =>
                                    e.innerText && e.innerText.trim() === text &&
                                    e.getBoundingClientRect().width > 0
                                );
                                if (el) { el.click(); return text; }
                            }
                            return null;
                        }""", texts)
                        if clicked:
                            break
                    except Exception:
                        pass
                if clicked:
                    log.debug("click JS fallback OK: text='%s'", clicked)
                else:
                    log.warn("click 실패 — 모든 방법 소진: %s", selector)
                    return False
            else:
                log.warn("click 실패 — 요소 없음: %s", selector)
                return False

    err = page_check_error(page, timeout=1500)
    if err:
        log.warn("click 후 에러: %s", err)
        return False
    return True


def page_click_then_wait(
    page: Page,
    click_selector: str,
    wait_selector: str,
    click_timeout: int = 15000,
    wait_timeout: int = 15000,
) -> bool:
    """클릭 → 결과 요소 vs 에러 요소 경쟁 감지. 먼저 나타나는 쪽으로 판단."""
    log.debug("click_then_wait: %s → %s", click_selector, wait_selector)
    try:
        el = page.wait_for_selector(click_selector, timeout=click_timeout, state="visible")
        el.click()
    except Exception:
        log.warn("click_then_wait: 클릭 요소 없음 — %s", click_selector)
        return False

    try:
        appeared = page.wait_for_selector(
            f"{wait_selector}, {_ERROR_SELECTORS}",
            timeout=wait_timeout,
            state="visible",
        )
        tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
        if any(k in tag_class for k in ("error", "alert", "toast")):
            msg = appeared.inner_text().strip()
            log.warn("click_then_wait: 에러 응답 — %s", msg)
            print(f"    ✗ 에러: {msg}")
            return False
        log.debug("click_then_wait: 결과 요소 확인")
        return True
    except Exception:
        log.warn("click_then_wait: 결과 요소 미등장 — %s", wait_selector)
        return False


def page_wait_type(
    page: Page,
    selector: str,
    text: str,
    timeout: int = 15000,
    delay: int = 40,
) -> bool:
    """입력창 대기 → 입력 → input_value() 검증.

    wait_for_selector 실패 시 JS dispatchEvent fallback (Angular Material 등 대응).
    """
    log.debug("wait_type: %s ← '%s'", selector, text[:30])
    el = None
    frame_used = page  # 실제 사용된 frame 추적
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        try:
            el.fill(text)
        except Exception:
            el.click(); el.click(); el.click()
            el.type(text, delay=delay)
    except Exception:
        # iframe 탐색 fallback
        found_frame, found_el = _find_frame(page, selector)
        if found_el:
            el = found_el
            frame_used = found_frame
            try:
                el.fill(text)
            except Exception:
                el.click(); el.click(); el.click()
                el.type(text, delay=delay)
            log.debug("type OK (iframe): %s", selector)
        else:
            # JS dispatchEvent fallback — 모든 frame 순회
            log.debug("type fallback JS: %s", selector)
            js_fill = """([sel, val]) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                el.focus();
                el.value = '';
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.value = val;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                return el.value;
            }"""
            result = None
            for frame in page.frames:
                try:
                    result = frame.evaluate(js_fill, [selector, text])
                    if result is not None:
                        frame_used = frame
                        break
                except Exception:
                    pass
            if result is None:
                log.warn("type 실패 — JS fallback도 요소 없음: %s", selector)
                return False
        if result != text:
            log.warn("type JS fallback 불일치 — 기대='%s' 실제='%s'", text[:30], str(result)[:30])
            print(f"    ⚠  입력값 불일치: 기대='{text}' 실제='{result}'")
            return False
        log.debug("type JS fallback OK: '%s'", text[:30])
        return True

    # wait_for_selector 성공 경로: input_value()로 검증
    try:
        actual = el.input_value()
        if actual == text:
            log.debug("type 검증 OK: '%s'", text[:30])
            return True
        log.warn("type 검증 실패 — 기대='%s' 실제='%s'", text[:30], actual[:30])
        print(f"    ⚠  입력값 불일치: 기대='{text}' 실제='{actual}'")
        return False
    except Exception:
        log.debug("type 검증 생략 (input_value 미지원): %s", selector)
        return True


def page_wait_nav(page: Page, url_pattern: str, timeout: int = 20000) -> bool:
    """URL 패턴 전환 대기."""
    log.debug("wait_nav: %s", url_pattern)
    try:
        page.wait_for_url(url_pattern, timeout=timeout)
        log.debug("nav OK: %s", url_pattern)
        return True
    except Exception:
        log.warn("nav 타임아웃: %s", url_pattern)
        return False


# ── 통합 감시 레이어 ──────────────────────────────────────────────────

@dataclass
class NetworkLog:
    """네트워크 감시 결과."""
    matched: list[dict] = field(default_factory=list)   # 매칭된 요청 목록
    errors:  list[dict] = field(default_factory=list)   # 4xx/5xx 응답


@contextmanager
def page_watch_network(
    page: Page,
    url_pattern: str = "",
    methods: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE"),
) -> Generator[NetworkLog, None, None]:
    """네트워크 요청 감시 컨텍스트.

    with page_watch_network(page, "/api/") as net:
        page_wait_click(page, "#save-btn")
    if net.matched:
        print("서버 요청 확인됨")

    url_pattern: 빈 문자열이면 모든 XHR/fetch 감시
    methods: 감시할 HTTP 메서드 (기본: 쓰기 요청만)
    """
    log_obj = NetworkLog()
    lock = threading.Lock()

    def on_response(response: Response) -> None:
        req = response.request
        if methods and req.method.upper() not in methods:
            return
        if url_pattern and url_pattern not in response.url:
            return
        entry = {
            "method": req.method,
            "url":    response.url,
            "status": response.status,
        }
        with lock:
            if response.status >= 400:
                log_obj.errors.append(entry)
                log.warn("network 에러 응답: %s %s → %d", req.method, response.url, response.status)
            else:
                log_obj.matched.append(entry)
                log.debug("network 요청 확인: %s %s → %d", req.method, response.url, response.status)

    page.on("response", on_response)
    try:
        yield log_obj
    finally:
        page.remove_listener("response", on_response)


@dataclass
class DomChangeLog:
    """DOM 변화 감시 결과."""
    changed: bool = False
    change_count: int = 0
    last_text: str = ""


@contextmanager
def page_watch_dom(
    page: Page,
    selector: str,
) -> Generator[DomChangeLog, None, None]:
    """DOM 변화 감시 컨텍스트 (MutationObserver).

    with page_watch_dom(page, "#result-area") as dom:
        page_wait_click(page, "#save-btn")
        time.sleep(0.5)  # 짧은 반응 대기
    if dom.changed:
        print(f"DOM 변화 확인: {dom.last_text}")
    """
    log_obj = DomChangeLog()

    # MutationObserver를 JS로 주입 — 변화 발생 시 window.__domChanged 플래그 설정
    js_inject = f"""
    (selector) => {{
        window.__domChanged = window.__domChanged || {{}};
        window.__domChanged[selector] = {{ count: 0, text: '' }};
        const target = document.querySelector(selector);
        if (!target) return false;
        const obs = new MutationObserver((mutations) => {{
            window.__domChanged[selector].count += mutations.length;
            window.__domChanged[selector].text = target.innerText || target.value || '';
        }});
        obs.observe(target, {{ childList: true, subtree: true, characterData: true, attributes: true }});
        window.__domObservers = window.__domObservers || {{}};
        window.__domObservers[selector] = obs;
        return true;
    }}
    """
    installed = page.evaluate(js_inject, selector)
    if not installed:
        log.warn("watch_dom: 셀렉터 없음 — %s", selector)

    try:
        yield log_obj
    finally:
        # 감시 결과 수집
        result = page.evaluate(
            "(sel) => window.__domChanged && window.__domChanged[sel]",
            selector
        )
        if result and result.get("count", 0) > 0:
            log_obj.changed = True
            log_obj.change_count = result["count"]
            log_obj.last_text = result.get("text", "")
            log.debug("dom 변화 확인: %s — %d회 변경, 최종='%s'",
                      selector, log_obj.change_count, log_obj.last_text[:50])

        # MutationObserver 해제
        page.evaluate(
            "(sel) => { if (window.__domObservers && window.__domObservers[sel]) "
            "window.__domObservers[sel].disconnect(); }",
            selector
        )


def page_poll_until(
    page: Page,
    selector: str,
    check_fn: Callable[[str], bool],
    interval: float = 0.5,
    timeout: float = 15.0,
) -> bool:
    """조건이 충족될 때까지 주기적으로 폴링.

    check_fn: 요소의 innerText/value를 받아 True/False 반환
    예) page_poll_until(page, "#status", lambda t: "저장됨" in t)
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            el = page.query_selector(selector)
            if el:
                text = ""
                try:
                    text = el.input_value()
                except Exception:
                    text = el.inner_text()
                if check_fn(text):
                    log.debug("poll_until 조건 충족: '%s'", text[:50])
                    return True
        except Exception:
            pass
        time.sleep(interval)

    log.warn("poll_until 타임아웃: %s", selector)
    return False


@dataclass
class VerifyResult:
    """page_submit_and_verify 결과."""
    success: bool = False
    network_ok: bool = False   # 서버 요청 2xx 확인
    dom_changed: bool = False  # UI DOM 변화 확인
    poll_ok: bool = False      # 최종 상태 폴링 확인
    error_msg: str = ""

    def summary(self) -> str:
        parts = []
        parts.append("네트워크 ✓" if self.network_ok  else "네트워크 ✗")
        parts.append("DOM변화 ✓"  if self.dom_changed  else "DOM변화 ✗")
        parts.append("폴링확인 ✓" if self.poll_ok      else "폴링확인 ✗")
        status = "성공" if self.success else "실패"
        return f"[{status}] {' | '.join(parts)}" + (f" | 에러={self.error_msg}" if self.error_msg else "")


def page_submit_and_verify(
    page: Page,
    submit_selector: str,
    *,
    network_pattern: str = "",
    dom_watch_selector: str = "",
    poll_selector: str = "",
    poll_check: Callable[[str], bool] | None = None,
    result_selector: str = "",
    submit_timeout: int = 10000,
    verify_timeout: float = 15.0,
) -> VerifyResult:
    """제출 버튼 클릭 후 3중 검증: 네트워크 요청 + DOM 변화 + 최종 폴링.

    사용 예:
        result = page_submit_and_verify(
            page,
            submit_selector='button:has-text("저장")',
            network_pattern="/api/",          # 서버 요청 URL 패턴
            dom_watch_selector="#result",     # 변화 감시할 DOM 요소
            poll_selector="#status-msg",      # 폴링할 요소
            poll_check=lambda t: "저장됨" in t,
            result_selector=".success-banner",
        )
        print(result.summary())
    """
    result = VerifyResult()

    # DOM 감시 대상 결정
    watch_sel = dom_watch_selector or result_selector or "body"

    with page_watch_network(page, url_pattern=network_pattern) as net:
        with page_watch_dom(page, watch_sel) as dom:
            # 제출 버튼 클릭
            try:
                btn = page.wait_for_selector(submit_selector, timeout=submit_timeout, state="visible")
                btn.click()
                log.debug("submit_and_verify: 클릭 완료 — %s", submit_selector)
            except Exception as e:
                result.error_msg = f"제출 버튼 없음: {e}"
                log.warn("submit_and_verify: %s", result.error_msg)
                return result

            # 결과 요소 vs 에러 경쟁 대기
            if result_selector:
                try:
                    appeared = page.wait_for_selector(
                        f"{result_selector}, {_ERROR_SELECTORS}",
                        timeout=int(verify_timeout * 1000),
                        state="visible",
                    )
                    tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
                    if any(k in tag_class for k in ("error", "alert", "toast")):
                        result.error_msg = appeared.inner_text().strip()
                        log.warn("submit_and_verify: 에러 응답 — %s", result.error_msg)
                        return result
                except Exception:
                    pass

            # DOM 변화 감지를 위해 짧게 대기
            time.sleep(0.8)

    # ── 검증 1: 네트워크 ──────────────────────────────────────────────
    if net.errors:
        result.error_msg = f"서버 에러: {net.errors[0]['status']} {net.errors[0]['url']}"
        log.warn("submit_and_verify: %s", result.error_msg)
        return result
    result.network_ok = bool(net.matched) or not network_pattern
    # network_pattern 미지정 시 감시 생략(항상 통과)

    # ── 검증 2: DOM 변화 ─────────────────────────────────────────────
    result.dom_changed = dom.changed
    if dom.changed:
        log.debug("submit_and_verify: DOM 변화 확인 (%d회)", dom.change_count)

    # ── 검증 3: 폴링 ─────────────────────────────────────────────────
    if poll_selector and poll_check:
        result.poll_ok = page_poll_until(
            page, poll_selector, poll_check,
            interval=0.5, timeout=verify_timeout
        )
    else:
        result.poll_ok = True  # 폴링 기준 미지정 시 생략

    # 에러 메시지 최종 확인
    err = page_check_error(page, timeout=1000)
    if err:
        result.error_msg = err
        return result

    result.success = result.network_ok and (result.dom_changed or not dom_watch_selector) and result.poll_ok
    return result


# ── 실시간 브라우저 상태 감시 ──────────────────────────────────────────

def page_inspect(page: Page, label: str = "") -> dict:
    """현재 페이지의 실제 요소 상태를 실시간으로 수집·출력.

    각 단계 진입 시 호출하면 실제 셀렉터를 파악할 수 있다.
    반환값: { url, title, inputs, buttons, errors }
    """
    tag = f"[inspect{':' + label if label else ''}]"

    result = page.evaluate("""() => {
        const inputs = Array.from(document.querySelectorAll('input:not([type=hidden])'))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            })
            .map(el => ({
                id:          el.id || '',
                name:        el.name || '',
                type:        el.type || '',
                placeholder: el.placeholder || '',
                value:       el.value || '',
                class:       el.className || '',
            }));

        const buttons = Array.from(document.querySelectorAll(
            'button, [role="button"], input[type=submit], a[role="button"]'
        ))
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0 && !el.disabled;
            })
            .map(el => ({
                text:  (el.innerText || el.value || '').trim().slice(0, 60),
                id:    el.id || '',
                class: el.className || '',
                role:  el.getAttribute('role') || '',
            }))
            .filter(b => b.text);

        const errors = Array.from(document.querySelectorAll(
            '[role="alert"], .mat-error, .error-message, .cfc-error'
        ))
            .map(el => el.innerText.trim())
            .filter(t => t);

        return { inputs, buttons, errors };
    }""")

    url   = page.url
    title = page.title()

    log.debug("%s URL=%s TITLE=%s", tag, url, title)
    print(f"  {tag} URL: {url}")
    print(f"  {tag} TITLE: {title}")

    inputs  = result.get("inputs", [])
    buttons = result.get("buttons", [])
    errors  = result.get("errors", [])

    if inputs:
        print(f"  {tag} INPUT ({len(inputs)}개):")
        for inp in inputs:
            print(f"    id={inp['id']!r:20} type={inp['type']!r:10} "
                  f"placeholder={inp['placeholder']!r:30} value={inp['value']!r}")
    else:
        print(f"  {tag} INPUT: 없음")

    if buttons:
        print(f"  {tag} BUTTON ({len(buttons)}개):")
        for btn in buttons[:10]:  # 최대 10개만 출력
            print(f"    text={btn['text']!r:40} id={btn['id']!r}")
    else:
        print(f"  {tag} BUTTON: 없음")

    if errors:
        print(f"  {tag} ERROR: {errors}")

    log.debug("%s inputs=%d buttons=%d errors=%d", tag, len(inputs), len(buttons), len(errors))
    return {"url": url, "title": title, "inputs": inputs, "buttons": buttons, "errors": errors}
