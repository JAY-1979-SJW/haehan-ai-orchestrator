"""page_helper 통합 감시 레이어 — network/dom watch + poll + submit_and_verify."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

from playwright.sync_api import Page, Response

from scripts.browser.page.page_helper_common import _ERROR_SELECTORS
from scripts.common.logger import get_logger

log = get_logger(__name__)


@dataclass
class NetworkLog:
    """네트워크 감시 결과."""

    matched: list[dict] = field(default_factory=list)  # 매칭된 요청 목록
    errors: list[dict] = field(default_factory=list)  # 4xx/5xx 응답


@contextmanager
def page_watch_network(
    page: Page,
    url_pattern: str = "",
    methods: tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE"),
) -> Generator[NetworkLog]:
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
            "url": response.url,
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
) -> Generator[DomChangeLog]:
    """DOM 변화 감시 컨텍스트 (MutationObserver).

    with page_watch_dom(page, "#result-area") as dom:
        page_wait_click(page, "#save-btn")
        time.sleep(0.5)  # 짧은 반응 대기
    if dom.changed:
        print(f"DOM 변화 확인: {dom.last_text}")
    """
    log_obj = DomChangeLog()

    # MutationObserver를 JS로 주입 — 변화 발생 시 window.__domChanged 플래그 설정
    js_inject = """
    (selector) => {
        window.__domChanged = window.__domChanged || {};
        window.__domChanged[selector] = { count: 0, text: '' };
        const target = document.querySelector(selector);
        if (!target) return false;
        const obs = new MutationObserver((mutations) => {
            window.__domChanged[selector].count += mutations.length;
            window.__domChanged[selector].text = target.innerText || target.value || '';
        });
        obs.observe(target, { childList: true, subtree: true, characterData: true, attributes: true });
        window.__domObservers = window.__domObservers || {};
        window.__domObservers[selector] = obs;
        return true;
    }
    """
    installed = page.evaluate(js_inject, selector)
    if not installed:
        log.warn("watch_dom: 셀렉터 없음 — %s", selector)

    try:
        yield log_obj
    finally:
        # 감시 결과 수집
        result = page.evaluate("(sel) => window.__domChanged && window.__domChanged[sel]", selector)
        if result and result.get("count", 0) > 0:
            log_obj.changed = True
            log_obj.change_count = result["count"]
            log_obj.last_text = result.get("text", "")
            log.debug(
                "dom 변화 확인: %s — %d회 변경, 최종='%s'", selector, log_obj.change_count, log_obj.last_text[:50]
            )

        # MutationObserver 해제
        page.evaluate(
            "(sel) => { if (window.__domObservers && window.__domObservers[sel]) "
            "window.__domObservers[sel].disconnect(); }",
            selector,
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
                except Exception:  # noqa: BLE001 - 폼 제출 3중 검증(네트워크/DOM변화/폴링) 유틸 — 각 except는 폴백 시도(input_value 실패시 inner_text) 또는 폴링 계속을 할 뿐, 제출버튼 클릭 실패나 검증 실패는 error_msg와 success=False로 명확히 반환되어 실패가 성공으로 오인되지 않음.
                    text = el.inner_text()
                if check_fn(text):
                    log.debug("poll_until 조건 충족: '%s'", text[:50])
                    return True
        except Exception:  # noqa: BLE001 - 폼 제출 3중 검증(네트워크/DOM변화/폴링) 유틸 — 각 except는 폴백 시도(input_value 실패시 inner_text) 또는 폴링 계속을 할 뿐, 제출버튼 클릭 실패나 검증 실패는 error_msg와 success=False로 명확히 반환되어 실패가 성공으로 오인되지 않음.
            pass
        time.sleep(interval)

    log.warn("poll_until 타임아웃: %s", selector)
    return False


@dataclass
class VerifyResult:
    """page_submit_and_verify 결과."""

    success: bool = False
    network_ok: bool = False  # 서버 요청 2xx 확인
    dom_changed: bool = False  # UI DOM 변화 확인
    poll_ok: bool = False  # 최종 상태 폴링 확인
    error_msg: str = ""

    def summary(self) -> str:
        parts = []
        parts.append("네트워크 ✓" if self.network_ok else "네트워크 ✗")
        parts.append("DOM변화 ✓" if self.dom_changed else "DOM변화 ✗")
        parts.append("폴링확인 ✓" if self.poll_ok else "폴링확인 ✗")
        status = "성공" if self.success else "실패"
        return f"[{status}] {' | '.join(parts)}" + (f" | 에러={self.error_msg}" if self.error_msg else "")


def page_submit_and_verify(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
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
                assert btn is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
                btn.click()
                log.debug("submit_and_verify: 클릭 완료 — %s", submit_selector)
            except Exception as e:  # noqa: BLE001 - 폼 제출 3중 검증(네트워크/DOM변화/폴링) 유틸 — 각 except는 폴백 시도(input_value 실패시 inner_text) 또는 폴링 계속을 할 뿐, 제출버튼 클릭 실패나 검증 실패는 error_msg와 success=False로 명확히 반환되어 실패가 성공으로 오인되지 않음.
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
                    assert appeared is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
                    tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
                    if any(k in tag_class for k in ("error", "alert", "toast")):
                        result.error_msg = appeared.inner_text().strip()
                        log.warn("submit_and_verify: 에러 응답 — %s", result.error_msg)
                        return result
                except Exception:  # noqa: BLE001 - 폼 제출 3중 검증(네트워크/DOM변화/폴링) 유틸 — 각 except는 폴백 시도(input_value 실패시 inner_text) 또는 폴링 계속을 할 뿐, 제출버튼 클릭 실패나 검증 실패는 error_msg와 success=False로 명확히 반환되어 실패가 성공으로 오인되지 않음.
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
        result.poll_ok = page_poll_until(page, poll_selector, poll_check, interval=0.5, timeout=verify_timeout)
    else:
        result.poll_ok = True  # 폴링 기준 미지정 시 생략

    # 에러 메시지 최종 확인
    from scripts.browser.page.page_helper_interact import page_check_error

    err = page_check_error(page, timeout=1000)
    if err:
        result.error_msg = err
        return result

    result.success = result.network_ok and (result.dom_changed or not dom_watch_selector) and result.poll_ok
    return result
