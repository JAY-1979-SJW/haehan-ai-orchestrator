"""페이지 팝업(모달 + 별도 창) 자동 감지 및 처리 — 사이트 무관 일반 모듈.

처리 대상:
  1. 별도 창 팝업 (window.open으로 열린 자식 페이지)
     - 휴리스틱: window.opener / URL 키워드 / title 키워드 / 작은 뷰포트
     - 보호 도메인 시스템으로 메인 작업 페이지 오인 닫힘 방지
  2. 모달 다이얼로그 (.modal, .popup, .pop_modal_cont, [role='dialog'] 등)
     - Playwright 네이티브 is_visible()로 실제 활성 팝업만 판별
     - 닫기 버튼: 팝업 내부 '닫기' 텍스트 / 클래스 기반 셀렉터 / ESC / 강제 hide

자동 후킹:
  page_helper.page_goto() / page_goto_wait()에서 자동 호출됨
  비활성화: page_helper.disable_auto_popup_handling()

보호 도메인 등록:
  from scripts.browser.popup.popup_detector import add_protected_domain
  add_protected_domain("my-main-app.com")  # 절대 닫히면 안 되는 도메인

사용법:
  from scripts.browser.popup.popup_detector import detect_popup, close_all_popups, handle_page_popups
  handle_page_popups(page)  # 별도 창 + 모달 모두 처리
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

from scripts.common.logger import get_logger

_log = get_logger(__name__)

# EUM 팝업 컨테이너 셀렉터 (우선순위 순)
POPUP_SELECTORS = [
    ".pop_modal_cont",  # EUM 전용
    "[class*='pop_modal']",
    "[class*='modal']",
    "[role='dialog']",
    "[aria-modal='true']",
    "[class*='popup']",
    "div.layer",
]

# 닫기 버튼 텍스트
CLOSE_TEXTS = ["닫기", "Close", "×", "X", "✕"]

# 닫기 버튼 셀렉터 (클래스 기반)
CLOSE_SELECTORS = [
    "button.close",
    "button.btn-close",
    "button.btn_close",
    ".btn_pop_close",
    ".btn_close_pop",
    "[class*='btn_close']",
    "button[aria-label*='닫기']",
    "button[aria-label*='close' i]",
    "button[title*='닫기']",
]

# 팝업 제외 클래스 키워드
EXCLUDE_KEYWORDS = ["chatbot", "header", "gnb", "lnb", "snb", "nav", "footer", "toast", "alert-bar"]

# 별도 창 팝업 URL/title 키워드 (사이트 무관 일반 패턴)
POPUP_WINDOW_URL_KEYWORDS = [
    "/popup/",
    "/pop/",
    "popup.do",
    "popup.html",
    "popup.jsp",
    "popup.aspx",
    "popup=",
    "isPopup",
    "is_popup",
    "/alert/",
    "/alarm/",
    "/notice/",
    "WEBCOM010P",  # EUM 공통 팝업 페이지 prefix
]
POPUP_WINDOW_TITLE_KEYWORDS = ["팝업", "알림", "공지사항", "Popup", "Alert", "Notice"]

# 보호 도메인 — 절대 닫지 말아야 할 메인 사이트
# (사용자가 작업 중인 사이트는 add_protected_domain()으로 동적 추가)
_PROTECTED_DOMAINS: set[str] = set()


def add_protected_domain(domain: str) -> None:
    """팝업으로 오인되어 닫히면 안 되는 도메인 등록.

    예: add_protected_domain("eum.cw.or.kr")
    """
    _PROTECTED_DOMAINS.add(domain.lower())


def _is_protected(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(d in url_lower for d in _PROTECTED_DOMAINS)


def _is_excluded(cls: str) -> bool:
    return any(k in cls for k in EXCLUDE_KEYWORDS)


def _get_visible_popups(page) -> list:
    """Playwright 네이티브 is_visible()로 실제 표시 중인 팝업 목록 반환"""
    visible = []
    for sel in POPUP_SELECTORS:
        try:
            locators = page.locator(sel)
            count = locators.count()
            for i in range(count):
                el = locators.nth(i)
                try:
                    if not el.is_visible(timeout=300):
                        continue
                    cls = el.get_attribute("class") or ""
                    if _is_excluded(cls):
                        continue
                    text = ""
                    # 여러 셀렉터를 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
                    with contextlib.suppress(Exception):
                        text = el.inner_text(timeout=500)[:80]
                    visible.append(
                        {
                            "selector": sel,
                            "index": i,
                            "cls": cls[:80],
                            "text": text,
                            "locator": el,
                        }
                    )
                except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
                    continue
        except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
            continue

    # 중복 제거 (text 기준)
    seen_texts = set()
    unique = []
    for p in visible:
        key = p["text"][:30]
        if key not in seen_texts:
            seen_texts.add(key)
            unique.append(p)

    return unique


def detect_popup(page) -> dict[str, Any]:
    """현재 페이지의 팝업 감지.

    Returns:
        {
            detected: bool,
            popup_count: int,
            types: list[str],
            elements: list[dict],
        }
    """
    try:
        popups = _get_visible_popups(page)

        _log.debug("[popup-detector] 팝업 감지: %d개", len(popups))
        for p in popups:
            _log.debug("  sel=%s cls=%s", p["selector"], p["cls"][:40])

        return {
            "detected": len(popups) > 0,
            "popup_count": len(popups),
            "types": list({p["selector"] for p in popups}),
            "elements": [{k: v for k, v in p.items() if k != "locator"} for p in popups],
        }

    except Exception as e:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
        _log.debug("[popup-detector] 팝업 감지 실패: %s", e)
        return {"detected": False, "popup_count": 0, "types": [], "elements": []}


def _close_by_text(container):
    for txt in CLOSE_TEXTS:
        try:
            btn = container.get_by_text(txt, exact=True)
            if btn.count() > 0 and btn.first.is_visible(timeout=300):
                btn.first.click(timeout=2000)
                time.sleep(0.8)
                _log.info("[popup-detector] 팝업 닫음: 텍스트버튼='%s'", txt)
                return {"closed": True, "method": f"text_button:{txt}"}
        except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
            continue
    return None


def _close_by_selector(container):
    for sel in CLOSE_SELECTORS:
        try:
            btn = container.locator(sel).first
            if btn.is_visible(timeout=300):
                btn.click(timeout=2000)
                time.sleep(0.8)
                _log.info("[popup-detector] 팝업 닫음: 셀렉터='%s'", sel)
                return {"closed": True, "method": f"selector:{sel}"}
        except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
            continue
    return None


def _close_by_global(page):
    for sel in CLOSE_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=300):
                btn.click(timeout=2000)
                time.sleep(0.8)
                _log.info("[popup-detector] 팝업 닫음: 전역셀렉터='%s'", sel)
                return {"closed": True, "method": f"global:{sel}"}
        except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
            continue
    return None


def close_popup(page) -> dict[str, Any]:
    """최상위 팝업 1개 닫기.

    전략:
      1. 팝업 내부 '닫기' 텍스트 버튼
      2. 클래스 기반 닫기 버튼 셀렉터
      3. ESC 키
      4. 팝업 요소 강제 hide
    """
    try:
        popups = _get_visible_popups(page)
        if not popups:
            return {"closed": False, "method": None, "reason": "no_popup"}

        top = popups[0]
        container = top["locator"]

        # 1. 팝업 내부 닫기 텍스트 버튼
        _early = _close_by_text(container)
        if _early is not None:
            return _early

        # 2. 클래스 기반 닫기 버튼 (팝업 내부)
        _early = _close_by_selector(container)
        if _early is not None:
            return _early

        # 3. 전역 닫기 버튼 (팝업 밖에서도 탐색)
        _early = _close_by_global(page)
        if _early is not None:
            return _early

        # 4. ESC
        page.keyboard.press("Escape")
        time.sleep(0.6)
        _log.info("[popup-detector] ESC 시도")
        # ESC 후 팝업 감소 확인
        after = _get_visible_popups(page)
        if len(after) < len(popups):
            return {"closed": True, "method": "esc_key"}

        # 5. 강제 hide
        count = _force_close_all(page)
        if count > 0:
            return {"closed": True, "method": "force_hide"}

        return {"closed": False, "method": None, "reason": "all_methods_failed"}

    except Exception as e:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
        _log.error("[popup-detector] 팝업 닫기 실패: %s", e)
        return {"closed": False, "method": None, "error": str(e)}


def close_all_popups(page, max_attempts: int = 10) -> dict[str, Any]:
    """페이지의 모든 팝업을 반복해서 닫기."""
    total_closed = 0
    prev_count = -1
    stuck = 0

    for attempt in range(max_attempts):
        popups = _get_visible_popups(page)
        count = len(popups)

        if count == 0:
            _log.info("[popup-detector] 모든 팝업 닫음 (%d회, %d개)", attempt, total_closed)
            break

        if count == prev_count:
            stuck += 1
            if stuck >= 3:
                _log.warning("[popup-detector] stuck — 강제 전체 제거")
                _force_close_all(page)
                break
        else:
            stuck = 0
        prev_count = count

        result = close_popup(page)
        if result.get("closed"):
            total_closed += 1
            time.sleep(1.0)
        else:
            _log.warning("[popup-detector] 닫기 실패 — 강제 전체 제거")
            _force_close_all(page)
            break

    # 잔여 dimmed 정리
    leftover = page.evaluate("""
    (() => {
        let n = 0;
        document.querySelectorAll('.dimmed, .dim, [class*="dimm"]').forEach(el => {
            const s = window.getComputedStyle(el);
            if (s.display !== 'none') { el.style.display = 'none'; n++; }
        });
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        return n;
    })();
    """)
    if leftover:
        _log.info("[popup-detector] dimmed 잔여 %d개 정리", leftover)

    final = detect_popup(page)
    return {
        "total_closed": total_closed,
        "attempts": attempt + 1 if "attempt" in dir() else 0,
        "final_state": final,
    }


def _force_close_all(page) -> int:
    """모든 팝업 요소 강제 숨김 (EUM pop_modal_cont 포함)"""
    count = page.evaluate("""
    (() => {
        let n = 0;
        const EXCLUDE = ['chatbot', 'header', 'gnb', 'lnb', 'snb', 'nav', 'footer'];
        function excluded(cls) { return EXCLUDE.some(k => cls.includes(k)); }

        // EUM 전용
        document.querySelectorAll('.pop_modal_cont').forEach(el => {
            el.style.display = 'none'; n++;
        });

        // 일반 모달
        ['[class*="modal"]', '[class*="popup"]', '[role="dialog"]', '[aria-modal="true"]', 'div.layer'].forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                const s = window.getComputedStyle(el);
                const z = parseInt(s.zIndex) || 0;
                const cls = el.className || '';
                if (s.display !== 'none' && z >= 50 && !excluded(cls)) {
                    el.style.display = 'none'; n++;
                }
            });
        });

        // dimmed 정리
        document.querySelectorAll('.dimmed, .dim, [class*="dimm"]').forEach(el => {
            el.style.display = 'none';
        });
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        return n;
    })();
    """)
    _log.info("[popup-detector] 강제 전체 제거: %d개", count)
    return count


def _title_keyword_popup(info, title, w, h):
    for kw in POPUP_WINDOW_TITLE_KEYWORDS:
        if kw in title:
            # opener도 있으면 거의 확실
            if info.get("hasOpener"):
                return True, f"title_kw_with_opener:{kw}"
            # title만으로는 약함 — 작은 창 크기 추가 조건
            if w > 0 and (w < 800 or h < 600):
                return True, f"title_kw_small:{kw}"
    return None


def _looks_like_popup_window(p) -> tuple[bool, str]:
    """페이지가 window.open()으로 열린 팝업창인지 휴리스틱 판단.

    판단 기준 (OR):
      1. window.opener 가 존재 (window.open으로 열림)
      2. URL에 popup 관련 키워드 포함
      3. title에 팝업/알림 키워드 포함
      4. 뷰포트가 작음 (< 800x600 으로 열린 팝업 창)

    Returns:
        (is_popup, reason)
    """
    try:
        url = p.url
    except Exception:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
        return False, "url_unavailable"

    # 보호 도메인은 무조건 제외
    if _is_protected(url):
        return False, "protected_domain"

    # about:blank 등은 팝업 아님 (작업 중일 수 있음)
    if not url or url in ("about:blank", "chrome://newtab/"):
        return False, "blank"

    # 1. URL 키워드
    url_lower = url.lower()
    for kw in POPUP_WINDOW_URL_KEYWORDS:
        if kw.lower() in url_lower:
            return True, f"url_keyword:{kw}"

    # 2. window.opener + viewport 크기 검사
    try:
        info = p.evaluate("""
        () => ({
            hasOpener: !!window.opener,
            w: window.innerWidth,
            h: window.innerHeight,
            title: document.title
        })
        """)
        title = info.get("title", "") or ""
        w = info.get("w", 0) or 0
        h = info.get("h", 0) or 0

        # 3. title 키워드
        _early = _title_keyword_popup(info, title, w, h)
        if _early is not None:
            return _early

        # 4. opener 있고 작은 창 (전형적인 window.open 팝업)
        if info.get("hasOpener") and w > 0 and (w < 800 or h < 600):
            return True, "opener_small_window"

    except Exception:  # noqa: BLE001 - 여러 셀렉터를 순차 시도하는 best-effort — 하나 실패해도 다음 방법으로 계속(2026-09-28 검토)
        pass

    return False, "not_popup"


def close_popup_windows(page) -> int:
    """별도 창(window.open) 팝업 자동 감지·닫기 — 사이트 무관 일반 휴리스틱.

    현재 page 자체는 닫지 않는다.
    """
    closed = 0
    try:
        ctx = page.context
        pages = list(ctx.pages)
        for p in pages:
            if p is page:
                continue
            is_popup, reason = _looks_like_popup_window(p)
            if is_popup:
                try:
                    url = p.url
                    p.close()
                    closed += 1
                    _log.info("[popup-detector] 별도 창 팝업 닫음 (%s): %s", reason, url[:80])
                except Exception as e:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
                    _log.warning("[popup-detector] 별도 창 닫기 실패: %s", e)
    except Exception as e:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
        _log.error("[popup-detector] 별도 창 팝업 처리 실패: %s", e)
    return closed


def handle_page_popups(page, timeout_s: float = 3.0) -> dict[str, Any]:
    """페이지 로드 후 자동으로 팝업 처리.

    처리 대상:
      1. window.open()으로 열린 별도 창 팝업 (BrowserContext의 다른 페이지)
      2. 현재 페이지의 모달 팝업 (.pop_modal_cont 등)
    """
    try:
        time.sleep(0.5)

        # 1. 별도 창 팝업 먼저 닫기 (메인 페이지 작업 방해 방지)
        windows_closed = close_popup_windows(page)
        if windows_closed:
            _log.info("[popup-detector] 별도 창 팝업 %d개 닫음", windows_closed)

        # 2. 현재 페이지의 모달 감지/닫기
        initial = detect_popup(page)
        modals_closed = 0
        if initial["detected"]:
            _log.info("[popup-detector] 모달 %d개 감지, 자동 처리 시작", initial["popup_count"])
            result = close_all_popups(page, max_attempts=10)
            modals_closed = result["total_closed"]
            final_clean = not result["final_state"]["detected"]
        else:
            final_clean = True

        total = windows_closed + modals_closed
        return {
            "had_popup": total > 0,
            "popups_closed": total,
            "windows_closed": windows_closed,
            "modals_closed": modals_closed,
            "page_clean": final_clean,
        }

    except Exception as e:  # noqa: BLE001 - 범용 팝업 감지·닫기 — 순수 UI 노이즈 제거, 실패는 {detected/closed: False, ...} 구조로 반환하거나 보호도메인은 무조건 제외, 쓰기·결제 없음(2026-09-28 검토)
        _log.error("[popup-detector] 페이지 팝업 처리 실패: %s", e)
        return {"had_popup": None, "popups_closed": 0, "page_clean": False, "error": str(e)}
