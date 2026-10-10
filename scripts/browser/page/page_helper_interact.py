"""page_helper 인터랙션 헬퍼 — click / type / check_error."""

from __future__ import annotations

import re

from playwright.sync_api import Page

from scripts.browser.page.page_helper_common import _ERROR_SELECTORS, _find_frame
from scripts.common.logger import get_logger

log = get_logger(__name__)


def page_check_error(page: Page, timeout: int = 1500) -> str | None:
    """에러 요소가 있으면 텍스트 반환, 없으면 None."""
    try:
        el = page.wait_for_selector(_ERROR_SELECTORS, timeout=timeout, state="visible")
        assert el is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
        msg = el.inner_text().strip()
        log.warn("에러 감지: %s", msg)
        return msg or "(에러 텍스트 없음)"
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        return None


def page_wait_click(page: Page, selector: str, timeout: int = 20000) -> bool:
    """요소 대기 → 클릭 → 클릭 직후 에러 감지.

    메인 프레임 실패 시 iframe 탐색 → JS 텍스트 fallback 순으로 시도.
    """
    log.debug("wait_click: %s", selector)
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        assert el is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
        el.click()
        log.debug("click OK: %s", selector)
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        # iframe 탐색 fallback
        frame, el = _find_frame(page, selector)
        if el:
            el.click()
            log.debug("click OK (iframe): %s", selector)
        else:
            # JS 텍스트 기반 클릭 fallback
            texts = re.findall(r'has-text\("([^"]+)"\)', selector)
            if texts:
                # 모든 frame에서 텍스트로 클릭 시도
                clicked = None
                for frame in page.frames:
                    try:
                        clicked = frame.evaluate(
                            """(texts) => {
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
                        }""",
                            texts,
                        )
                        if clicked:
                            break
                    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
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
        assert el is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
        el.click()
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        log.warn("click_then_wait: 클릭 요소 없음 — %s", click_selector)
        return False

    try:
        appeared = page.wait_for_selector(
            f"{wait_selector}, {_ERROR_SELECTORS}",
            timeout=wait_timeout,
            state="visible",
        )
        assert appeared is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
        tag_class = (appeared.get_attribute("class") or "") + (appeared.get_attribute("role") or "")
        if any(k in tag_class for k in ("error", "alert", "toast")):
            msg = appeared.inner_text().strip()
            log.warn("click_then_wait: 에러 응답 — %s", msg)
            print(f"    ✗ 에러: {msg}")
            return False
        log.debug("click_then_wait: 결과 요소 확인")
        return True
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        log.warn("click_then_wait: 결과 요소 미등장 — %s", wait_selector)
        return False


def _fill_or_type(el, text: str, delay: int) -> None:
    try:
        el.fill(text)
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        el.click()
        el.click()
        el.click()
        el.type(text, delay=delay)


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
    try:
        el = page.wait_for_selector(selector, timeout=timeout, state="visible")
        assert el is not None  # state="visible" 대기 성공 시 항상 핸들 반환(Playwright)
        _fill_or_type(el, text, delay)
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        # iframe 탐색 fallback
        _found_frame, found_el = _find_frame(page, selector)
        if found_el:
            el = found_el
            _fill_or_type(el, text, delay)
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
                        break
                except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
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
    except Exception:  # noqa: BLE001 - 범용 페이지 클릭/타입 헬퍼(iframe 폴백 포함) - 실패시 False 반환 또는 대체 방법 시도, 결제/삭제 없음
        log.debug("type 검증 생략 (input_value 미지원): %s", selector)
        return True
