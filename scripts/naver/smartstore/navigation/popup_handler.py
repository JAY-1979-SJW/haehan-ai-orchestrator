"""스마트스토어 셀러센터 팝업 감지·처리 모듈.

감지 대상:
  1. 공지 레이어 팝업 (.seller-notice.seller-layer-modal)
     - "하루동안 보지 않기" 체크 후 닫기
  2. 일반 모달 ([role='dialog'], [class*='modal'])
  3. 별도 창 팝업 (window.open)

사용:
    from scripts.naver.smartstore.navigation.popup_handler import dismiss_all_popups
    result = dismiss_all_popups(page)
    # {"closed": int, "had_popup": bool, "page_clean": bool}

범용 popup_detector와 연동:
    - 스마트스토어 전용 패턴 먼저 시도
    - 실패 시 popup_detector.handle_page_popups() fallback
"""
from __future__ import annotations

import time
from pathlib import Path

from scripts.logger import get_logger

_log = get_logger(__name__)

# ── 셀러센터 전용 팝업 셀렉터 ─────────────────────────────────────────────────

# 공지 레이어 팝업 (가장 흔함)
NOTICE_POPUP_SELS = [
    ".seller-notice.seller-layer-modal",
    ".seller-layer-modal",
    ".seller-notice",
]

# 닫기 버튼
CLOSE_BTN_SELS = [
    "button.close",
    ".seller-layer-modal button.close",
    ".seller-notice button.close",
    "button[aria-label*='닫기']",
    "button[title*='닫기']",
    ".btn-close",
]

# "하루동안 보지 않기" 체크박스
TODAY_HIDE_SEL = "input[name='again']"

# 일반 모달 (Angular/Vue 기반)
GENERAL_MODAL_SELS = [
    "[role='dialog']",
    "[aria-modal='true']",
    "[class*='modal']:not(.seller-navbar):not(.seller-side-nav)",
    "[class*='Modal']:not(.seller-navbar)",
    "[class*='layer-modal']",
]

# 닫기 텍스트
CLOSE_TEXTS = ["닫기", "확인", "×", "X", "✕", "Close"]


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def detect_popups(page) -> dict:
    """현재 셀러센터 페이지의 팝업 감지."""
    notice   = _detect_notice_popup(page)
    general  = _detect_general_modals(page)
    windows  = _count_popup_windows(page)

    total = (1 if notice["detected"] else 0) + general["count"] + windows
    return {
        "detected": total > 0,
        "total": total,
        "notice_popup": notice,
        "general_modals": general,
        "popup_windows": windows,
    }


def dismiss_all_popups(page, check_today_hide: bool = True) -> dict:
    """셀러센터 모든 팝업 처리.

    Args:
        check_today_hide: True면 '하루동안 보지 않기' 체크 후 닫기

    Returns:
        {"closed": int, "had_popup": bool, "page_clean": bool}
    """
    closed = 0

    # 1. 별도 창 팝업
    win_closed = _close_popup_windows(page)
    closed += win_closed

    # 2. 공지 레이어 팝업 (셀러센터 전용)
    for _ in range(5):
        notice = _detect_notice_popup(page)
        if not notice["detected"]:
            break
        ok = _close_notice_popup(page, check_today_hide=check_today_hide)
        if ok:
            closed += 1
            time.sleep(0.8)
        else:
            break

    # 3. 일반 모달
    for _ in range(5):
        modals = _detect_general_modals(page)
        if modals["count"] == 0:
            break
        ok = _close_general_modal(page)
        if ok:
            closed += 1
            time.sleep(0.6)
        else:
            break

    # 4. fallback — 범용 popup_detector
    if closed == 0:
        try:
            from scripts.popup_detector import handle_page_popups
            fb = handle_page_popups(page)
            closed += fb.get("popups_closed", 0)
        except Exception as e:
            _log.debug("[ss-popup] fallback 실패: %s", e)

    # 5. 잔여 dimmed/backdrop 정리
    _cleanup_backdrop(page)

    final = detect_popups(page)
    _log.info("[ss-popup] 처리 완료: closed=%d had=%s clean=%s",
              closed, closed > 0, not final["detected"])
    return {
        "closed": closed,
        "had_popup": closed > 0,
        "page_clean": not final["detected"],
    }


# ── 내부: 공지 팝업 ──────────────────────────────────────────────────────────

def _detect_notice_popup(page) -> dict:
    for sel in NOTICE_POPUP_SELS:
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=300):
                txt = ""
                try:
                    txt = el.inner_text(timeout=500)[:100]
                except Exception:
                    pass
                return {"detected": True, "selector": sel, "text": txt}
        except Exception:
            pass
    return {"detected": False}


def _close_notice_popup(page, check_today_hide: bool = True) -> bool:
    """공지 팝업 닫기. check_today_hide=True면 '하루동안 보지 않기' 먼저 체크."""

    # 하루동안 보지 않기 체크
    if check_today_hide:
        try:
            cb = page.locator(TODAY_HIDE_SEL).first
            if cb.count() > 0 and cb.is_visible(timeout=300):
                if not cb.is_checked(timeout=300):
                    cb.click(timeout=2000)
                    time.sleep(0.3)
                    _log.info("[ss-popup] '하루동안 보지 않기' 체크")
        except Exception as e:
            _log.debug("[ss-popup] 체크박스 처리 실패: %s", e)

    # 닫기 버튼 클릭
    for sel in CLOSE_BTN_SELS:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible(timeout=300):
                btn.click(timeout=2000)
                time.sleep(0.5)
                _log.info("[ss-popup] 공지 팝업 닫음: %s", sel)
                return True
        except Exception:
            pass

    # 텍스트 기반 닫기
    for txt in CLOSE_TEXTS:
        try:
            btn = page.get_by_text(txt, exact=True).first
            if btn.count() > 0 and btn.is_visible(timeout=300):
                btn.click(timeout=2000)
                time.sleep(0.5)
                _log.info("[ss-popup] 텍스트 닫기: '%s'", txt)
                return True
        except Exception:
            pass

    # ESC
    page.keyboard.press("Escape")
    time.sleep(0.5)
    after = _detect_notice_popup(page)
    if not after["detected"]:
        _log.info("[ss-popup] ESC로 닫음")
        return True

    return False


# ── 내부: 일반 모달 ──────────────────────────────────────────────────────────

def _detect_general_modals(page) -> dict:
    count = 0
    found = []
    for sel in GENERAL_MODAL_SELS:
        try:
            els = page.locator(sel)
            n = els.count()
            for i in range(min(n, 3)):
                try:
                    el = els.nth(i)
                    if el.is_visible(timeout=200):
                        cls = el.get_attribute("class") or ""
                        # 네비게이션 요소 제외
                        if any(x in cls for x in ["navbar", "side-nav", "dock-nav", "backdrop"]):
                            continue
                        count += 1
                        found.append({"selector": sel, "index": i})
                except Exception:
                    pass
        except Exception:
            pass
    return {"count": count, "found": found}


def _close_general_modal(page) -> bool:
    for sel in GENERAL_MODAL_SELS:
        try:
            modal = page.locator(sel).first
            if not (modal.count() > 0 and modal.is_visible(timeout=200)):
                continue
            cls = modal.get_attribute("class") or ""
            if any(x in cls for x in ["navbar", "side-nav", "dock-nav", "backdrop"]):
                continue

            # 닫기 버튼 (모달 내부)
            for close_sel in CLOSE_BTN_SELS:
                try:
                    btn = modal.locator(close_sel).first
                    if btn.count() > 0 and btn.is_visible(timeout=200):
                        btn.click(timeout=2000)
                        time.sleep(0.5)
                        return True
                except Exception:
                    pass

            # 텍스트 닫기
            for txt in CLOSE_TEXTS:
                try:
                    btn = modal.get_by_text(txt, exact=True).first
                    if btn.count() > 0 and btn.is_visible(timeout=200):
                        btn.click(timeout=2000)
                        time.sleep(0.5)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

    page.keyboard.press("Escape")
    time.sleep(0.5)
    return True


# ── 내부: 별도 창 팝업 ───────────────────────────────────────────────────────

def _count_popup_windows(page) -> int:
    try:
        from scripts.popup_detector import _looks_like_popup_window
        pages = page.context.pages
        return sum(1 for p in pages if p is not page and _looks_like_popup_window(p)[0])
    except Exception:
        return 0


def _close_popup_windows(page) -> int:
    try:
        from scripts.popup_detector import close_popup_windows
        return close_popup_windows(page)
    except Exception:
        return 0


# ── 내부: backdrop 정리 ──────────────────────────────────────────────────────

def _cleanup_backdrop(page) -> None:
    try:
        page.evaluate("""
        () => {
            document.querySelectorAll(
                ".seller-backdrop, .modal-backdrop, .dimmed, .dim, [class*='dimm']"
            ).forEach(el => {
                const s = window.getComputedStyle(el);
                if (s.display !== "none" && s.opacity !== "0") {
                    el.style.display = "none";
                }
            });
            document.body.style.overflow = "";
        }
        """)
    except Exception:
        pass
