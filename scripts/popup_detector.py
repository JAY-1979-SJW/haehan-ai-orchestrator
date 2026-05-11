"""페이지 팝업(모달, 알림) 자동 감지 및 처리.

지원하는 팝업 유형:
  - 모달 다이얼로그 (div.modal, [role="dialog"])
  - 기본 alert/confirm
  - 알림 배너
  - 광고 팝업

사용법:
  from scripts.popup_detector import detect_popup, close_all_popups, handle_page_popups

  # 팝업 감지
  has_popup = detect_popup(page)

  # 모든 팝업 닫기
  closed = close_all_popups(page)

  # 페이지 로드 후 팝업 자동 처리
  handle_page_popups(page)
"""
from __future__ import annotations

import time
from typing import Any

from scripts.logger import get_logger

_log = get_logger(__name__)

# 팝업 요소 셀렉터 목록
POPUP_SELECTORS = {
    "modal": [
        "div.modal",
        "[role='dialog']",
        ".modal-dialog",
        ".popup",
        ".layer",
        "[class*='modal']",
        "[class*='popup']",
        "[class*='dialog']",
    ],
    "overlay": [
        ".modal-overlay",
        ".dimmed",
        "[class*='overlay']",
    ],
}

# 닫기 버튼 셀렉터 (우선순위 순)
CLOSE_BUTTON_SELECTORS = [
    "button.close",
    "button.btn-close",
    "button[aria-label*='close' i]",
    "button[aria-label*='닫기' i]",
    "a.close",
    ".btn_pop_close",
    ".btn_close_pop",
    "button.btn_l.btn_ty",
    "button[class*='btn_ty']",
    "[class*='close']",
    "button:contains('닫기')",
    "button:contains('Close')",
    "button:contains('확인')",
]


def detect_popup(page) -> dict[str, Any]:
    """현재 페이지의 팝업 감지.

    Returns:
        {
            detected: bool,
            popup_count: int,
            types: list[str],  # 감지된 팝업 유형
            elements: list[dict],  # 팝업 요소 정보
        }
    """
    try:
        result = page.evaluate("""
        (() => {
            const detected = {
                modals: [],
                overlays: [],
                alerts: [],
            };

            // 모달 감지
            const modals = document.querySelectorAll(`
                div.modal,
                [role="dialog"],
                .modal-dialog,
                .popup,
                .layer
            `);
            modals.forEach(m => {
                const style = window.getComputedStyle(m);
                const visible = style.display !== 'none' && style.visibility !== 'hidden';
                if (visible) {
                    detected.modals.push({
                        tag: m.tagName,
                        className: m.className,
                        text: (m.innerText || '').substring(0, 100),
                        visible: true,
                    });
                }
            });

            // 오버레이/배경 감지
            const overlays = document.querySelectorAll('.modal-overlay, .dimmed, [class*="overlay"]');
            overlays.forEach(o => {
                const style = window.getComputedStyle(o);
                if (style.display !== 'none') {
                    detected.overlays.push({
                        className: o.className,
                    });
                }
            });

            // Close 버튼이 있는지 확인 (모달이 없어도 close 버튼이 있으면 팝업으로 간주)
            const closeSelectors = [
                "button.close",
                "button.btn-close",
                "button[aria-label*='close' i]",
                "button[aria-label*='닫기' i]",
                "a.close",
                ".btn_pop_close",
                ".btn_close_pop",
                "button.btn_l.btn_ty",
                "button[class*='btn_ty']",
            ];

            let hasCloseButton = false;
            for (const sel of closeSelectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    hasCloseButton = true;
                    break;
                }
            }

            detected.hasCloseButton = hasCloseButton;

            return detected;
        })();
        """)

        popup_count = len(result.get("modals", [])) + len(result.get("overlays", []))
        # 모달이 없어도 close 버튼이 있으면 팝업 감지로 처리
        has_popup = popup_count > 0 or result.get("hasCloseButton", False)

        types = []
        if result.get("modals"):
            types.append("modal")
        if result.get("overlays"):
            types.append("overlay")
        if result.get("hasCloseButton") and not types:
            types.append("close_button")

        _log.debug("[popup-detector] 팝업 감지: 모달=%d, 오버레이=%d, close버튼=%s",
                  len(result.get("modals", [])),
                  len(result.get("overlays", [])),
                  result.get("hasCloseButton", False))

        return {
            "detected": has_popup,
            "popup_count": popup_count if popup_count > 0 else (1 if result.get("hasCloseButton") else 0),
            "types": types,
            "elements": result.get("modals", []),
        }

    except Exception as e:
        _log.debug("[popup-detector] 팝업 감지 실패: %s", e)
        return {
            "detected": False,
            "popup_count": 0,
            "types": [],
            "elements": [],
        }


def close_popup(page) -> dict[str, Any]:
    """현재 가시화된 팝업 닫기.

    Returns:
        {
            closed: bool,
            method: str,  # 닫은 방법 (close_button, esc_key, etc)
            error: str,   # 실패 사유
        }
    """
    try:
        # 1. 닫기 버튼 찾기
        close_result = page.evaluate("""
        (() => {
            const selectors = [
                "button.close",
                "button.btn-close",
                "button[aria-label*='close' i]",
                "button[aria-label*='닫기' i]",
                "a.close",
                ".btn_pop_close",
                "[class*='close'][onclick]",
            ];

            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {  // 가시화됨
                    btn.click();
                    return { closed: true, method: 'close_button', selector: sel };
                }
            }

            // 2. 확인 버튼 클릭
            const confirmBtn = Array.from(document.querySelectorAll('button')).find(b =>
                (b.innerText || '').includes('확인') ||
                (b.innerText || '').includes('OK')
            );
            if (confirmBtn && confirmBtn.offsetParent !== null) {
                confirmBtn.click();
                return { closed: true, method: 'confirm_button' };
            }

            return { closed: false, method: null, reason: 'no_close_button_found' };
        })();
        """)

        if close_result.get("closed"):
            _log.info("[popup-detector] 팝업 닫음: %s", close_result.get("method"))
            return close_result
        else:
            # 3. ESC 키로 시도
            page.keyboard.press("Escape")
            time.sleep(0.5)
            _log.info("[popup-detector] ESC 키로 팝업 닫기 시도")
            return {
                "closed": True,
                "method": "esc_key",
            }

    except Exception as e:
        _log.error("[popup-detector] 팝업 닫기 실패: %s", e)
        return {
            "closed": False,
            "method": None,
            "error": str(e),
        }


def close_all_popups(page, max_attempts: int = 5) -> dict[str, Any]:
    """페이지의 모든 팝업을 반복해서 닫기.

    Args:
        page: Playwright Page
        max_attempts: 최대 닫기 시도 횟수

    Returns:
        {
            total_closed: int,
            attempts: int,
            final_state: dict,  # detect_popup() 결과
        }
    """
    total_closed = 0
    for attempt in range(max_attempts):
        detection = detect_popup(page)
        if not detection["detected"]:
            _log.info("[popup-detector] 모든 팝업 닫음 (%d회 시도)", attempt)
            return {
                "total_closed": total_closed,
                "attempts": attempt,
                "final_state": detection,
            }

        close_result = close_popup(page)
        if close_result.get("closed"):
            total_closed += 1
            time.sleep(0.5)
        else:
            _log.warning("[popup-detector] 팝업 닫기 실패: %s", close_result.get("error"))
            break

    return {
        "total_closed": total_closed,
        "attempts": max_attempts,
        "final_state": detect_popup(page),
    }


def handle_page_popups(page, timeout_s: float = 3.0) -> dict[str, Any]:
    """페이지 로드 후 자동으로 팝업 처리.

    페이지 진입 시 표시되는 팝업을 감지하고 자동으로 닫습니다.

    Args:
        page: Playwright Page
        timeout_s: 팝업 감지 대기 시간 (초)

    Returns:
        {
            had_popup: bool,
            popups_closed: int,
            page_clean: bool,
        }
    """
    try:
        start = time.time()

        # 초기 대기 (팝업 로드 대기)
        time.sleep(0.5)

        # 팝업 감지
        initial = detect_popup(page)

        if not initial["detected"]:
            _log.debug("[popup-detector] 팝업 없음")
            return {
                "had_popup": False,
                "popups_closed": 0,
                "page_clean": True,
            }

        _log.info("[popup-detector] %d개 팝업 감지, 자동 처리 시작", initial["popup_count"])

        # 모든 팝업 닫기
        result = close_all_popups(page, max_attempts=3)

        elapsed = time.time() - start
        _log.info("[popup-detector] 팝업 처리 완료 (%d개, %.1f초)", result["total_closed"], elapsed)

        return {
            "had_popup": True,
            "popups_closed": result["total_closed"],
            "page_clean": not result["final_state"]["detected"],
            "elapsed_s": elapsed,
        }

    except Exception as e:
        _log.error("[popup-detector] 페이지 팝업 처리 실패: %s", e)
        return {
            "had_popup": None,
            "popups_closed": 0,
            "page_clean": False,
            "error": str(e),
        }
