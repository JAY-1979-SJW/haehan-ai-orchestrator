"""Naver live browser safety guards.

Naver does not provide a dependable official API for the current workflows, so
browser use must be conservative: dry-run/static work by default, explicit live
approval for live reads, and immediate stop on robot/captcha/security signals.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

ROBOT_SIGNAL_PATTERNS = [
    r"로봇",
    r"자동\s*입력",
    r"자동화",
    r"비정상\s*(?:접근|활동|이용|트래픽)",
    r"보안\s*문자",
    r"보안\s*확인",
    r"본인\s*확인",
    r"추가\s*인증",
    r"2\s*단계\s*인증",
    r"2\s*차\s*인증",
    r"captcha",
    r"recaptcha",
    r"unusual\s+traffic",
    r"automated\s+queries",
    r"robot",
]

SECURITY_SELECTOR_JS = r"""
() => {
  const selectors = [
    'img[id*="captcha" i]',
    'img[src*="captcha" i]',
    'input[name*="captcha" i]',
    'input[id*="captcha" i]',
    '[class*="captcha" i]',
    '[id*="captcha" i]',
    'iframe[src*="captcha" i]',
    'iframe[src*="recaptcha" i]'
  ];
  return selectors.some((selector) => document.querySelector(selector));
}
"""


class NaverLiveSafetyBlocked(RuntimeError):
    """Raised when a live Naver browser operation must stop."""

    def __init__(self, result: dict[str, Any]):
        self.result = result
        super().__init__(result.get("reason") or "naver_live_safety_blocked")


@dataclass(frozen=True)
class LivePolicy:
    site: str = "naver"
    workflow: str = ""
    min_interval_s: float = 3.0
    require_live_ok: bool = True


_LAST_TOUCH: dict[str, float] = {}


def _emit(event_type: str, *, site: str, workflow: str, status: str, message: str, metadata: dict[str, Any]) -> None:
    try:
        from scripts.common.realtime_audit import emit_event

        emit_event(
            event_type,
            site=site,
            workflow=workflow,
            status=status,
            risk="live_browser",
            message=message,
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001 - 감사이벤트(emit) 전송은 부가 로깅일 뿐이라 실패해도 안전판정 로직에 영향 없어 무시
        pass


def detect_robot_signal(text: str, *, url: str = "", title: str = "") -> dict[str, Any]:
    probe = "\n".join([title or "", url or "", text or ""])
    for pattern in ROBOT_SIGNAL_PATTERNS:
        if re.search(pattern, probe, flags=re.IGNORECASE):
            return {
                "ok": False,
                "detected": True,
                "reason": "robot_or_security_signal",
                "matched_pattern": pattern,
                "url": url,
                "title": title,
            }
    return {"ok": True, "detected": False, "url": url, "title": title}


def require_live_flag(args: list[str], *, workflow: str, multi_target: bool = False) -> None:
    if "--live-ok" not in args and os.environ.get("NAVER_LIVE_OK") != "1":
        raise SystemExit(f"{workflow} live browser access requires --live-ok")
    if multi_target and "--allow-multi-target" not in args:
        raise SystemExit(f"{workflow} multi-target live scan requires --allow-multi-target")


def throttle_live(site: str, *, workflow: str = "", min_interval_s: float = 3.0) -> None:
    key = f"{site}:{workflow}"
    now = time.monotonic()
    last = _LAST_TOUCH.get(key)
    if last is not None:
        delay = min_interval_s - (now - last)
        if delay > 0:
            time.sleep(delay)
    _LAST_TOUCH[key] = time.monotonic()


def inspect_page(page, *, site: str = "naver", workflow: str = "", phase: str = "") -> dict[str, Any]:
    try:
        snapshot = page.evaluate(
            r"""() => ({
              url: location.href,
              title: document.title,
              text: String(document.body?.innerText || '').slice(0, 5000)
            })"""
        )
    except Exception as exc:  # noqa: BLE001 - 네이버 라이브 브라우저 안전가드(로봇/캡차 감지) — 감사이벤트 emit 실패는 무시(부가 로깅), 페이지 snapshot 평가 실패는 에러를 담아 텍스트 패턴 검사로 계속 보완, 셀렉터 감지 실패는 미탐지로 처리되지만 텍스트패턴 기반 detect_robot_signal이 별도로 최종 판정하며 ensure_page_safe는 result.ok=False면 예외를 던져 차단하는 fail-closed 구조
        snapshot = {"url": getattr(page, "url", ""), "title": "", "text": "", "error": str(exc)[:200]}

    result = detect_robot_signal(
        snapshot.get("text") or "",
        url=snapshot.get("url") or getattr(page, "url", ""),
        title=snapshot.get("title") or "",
    )

    selector_detected = False
    try:
        selector_detected = bool(page.evaluate(SECURITY_SELECTOR_JS))
    except Exception:  # noqa: BLE001 - 네이버 라이브 브라우저 안전가드(로봇/캡차 감지) — 감사이벤트 emit 실패는 무시(부가 로깅), 페이지 snapshot 평가 실패는 에러를 담아 텍스트 패턴 검사로 계속 보완, 셀렉터 감지 실패는 미탐지로 처리되지만 텍스트패턴 기반 detect_robot_signal이 별도로 최종 판정하며 ensure_page_safe는 result.ok=False면 예외를 던져 차단하는 fail-closed 구조
        selector_detected = False
    if selector_detected:
        result = {
            **result,
            "ok": False,
            "detected": True,
            "reason": "captcha_selector_detected",
        }

    if result.get("detected"):
        metadata = {
            "phase": phase,
            "url": result.get("url"),
            "title": result.get("title"),
            "matched_pattern": result.get("matched_pattern"),
            "reason": result.get("reason"),
        }
        _emit(
            "NAVER_ROBOT_DETECTED",
            site=site,
            workflow=workflow,
            status="blocked",
            message="Naver robot/security signal detected; live automation stopped",
            metadata=metadata,
        )
    return result


def ensure_page_safe(page, *, site: str = "naver", workflow: str = "", phase: str = "") -> dict[str, Any]:
    result = inspect_page(page, site=site, workflow=workflow, phase=phase)
    if not result.get("ok"):
        raise NaverLiveSafetyBlocked(result)
    return result


def before_live_navigation(args: list[str], *, site: str = "naver", workflow: str, multi_target: bool = False) -> None:
    require_live_flag(args, workflow=workflow, multi_target=multi_target)
    throttle_live(site, workflow=workflow)
