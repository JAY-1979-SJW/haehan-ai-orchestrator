"""봇 감지 레이더 — 사이트가 우릴 봇으로 보는지 자동 감지.

두 모드:
  1. scan(page)        : 현재 페이지 상태 1회 스캔. 적극+수동 신호.
  2. arm(page)         : 이벤트 훅 장착 (response, console, request) — 지속 감시
                          → get_signals() 로 누적 신호 회수.

반환:
  {
    "flagged": bool,                # 명백히 차단/도전장
    "confidence": float (0~1),
    "level": "clean|monitored|challenged|blocked",
    "vendors": [...],               # 감지된 봇 탐지 벤더들
    "signals": [{kind, detail, severity}],
  }

severity: low(0.1) | medium(0.4) | high(0.8) | critical(1.0)

사용 (자동 호출 — site_watch 에 통합 예정):
    from scripts.form.bot_radar import scan, BotDetected
    r = scan(page)
    if r["flagged"]:
        raise BotDetected(r)
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from scripts.common.logger import get_logger

log = get_logger(__name__)


class BotDetected(RuntimeError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__(
            f"봇 감지: level={report['level']} confidence={report['confidence']:.2f} "
            f"vendors={report.get('vendors', [])}"
        )


# ── 벤더 시그니처 ──────────────────────────────────────────────────
_VENDORS = {
    "cloudflare_bot": {
        "cookies": ["__cf_bm", "cf_chl_", "cf_clearance"],
        "scripts": ["/cdn-cgi/challenge-platform/", "challenges.cloudflare.com"],
        "urls": ["/cdn-cgi/challenge", "/cdn-cgi/l/chk_"],
        "html": ["cf-browser-verification", "cf-im-under-attack"],
    },
    "perimeterx": {
        "cookies": ["_pxhd", "_pxvid", "_px3", "pxcts"],
        "scripts": ["client.perimeterx.net", "/_px/"],
        "urls": ["/_px/captcha", "/_pxhd"],
        "html": ["perimeterx-captcha"],
    },
    "akamai_bot": {
        "cookies": ["_abck", "bm_sz", "ak_bmsc", "bm_mi"],
        "scripts": ["/akam/", "akamaihd.net/akam"],
        "urls": ["/akam/"],
        "html": [],
    },
    "datadome": {
        "cookies": ["datadome"],
        "scripts": ["js.datadome.co", "datadome-static"],
        "urls": ["/captcha/datadome"],
        "html": ["datadome-captcha"],
    },
    "imperva_incapsula": {
        "cookies": ["incap_ses_", "visid_incap_", "nlbi_"],
        "scripts": ["/_Incapsula_Resource", "_iiris"],
        "urls": ["/_Incapsula_Resource"],
        "html": ["Incapsula"],
    },
    "recaptcha": {
        "cookies": [],
        "scripts": ["/recaptcha/api.js", "google.com/recaptcha"],
        "urls": [],
        "html": ["g-recaptcha", "grecaptcha"],
    },
    "hcaptcha": {
        "cookies": ["hcaptcha"],
        "scripts": ["hcaptcha.com/1/api.js", "js.hcaptcha.com"],
        "urls": [],
        "html": ["h-captcha", "hcaptcha-box"],
    },
    "arkose_funcaptcha": {
        "cookies": [],
        "scripts": ["funcaptcha.com", "arkoselabs.com"],
        "urls": ["/v2/games/"],
        "html": ["FunCaptcha", "funcaptcha"],
    },
    "cloudflare_turnstile": {
        "cookies": [],
        "scripts": ["challenges.cloudflare.com/turnstile"],
        "urls": [],
        "html": ["cf-turnstile"],
    },
}

# ── 차단 텍스트 패턴 (한/영) ──────────────────────────────────────
_BLOCK_TEXT_PATTERNS = [
    (r"비정상\s*접근|비정상적인\s*접근", "high"),
    (r"자동화\s*감지|자동\s*로그인\s*차단", "critical"),
    (r"수상한\s*트래픽|의심스러운\s*활동", "high"),
    (r"잠시\s*후\s*다시\s*시도|일시적\s*차단", "high"),
    (r"로그인\s*시도.*초과|계정.*잠금", "high"),
    (r"보안\s*인증|보안문자|자동\s*입력\s*방지", "medium"),
    (r"unusual\s+(traffic|activity)|suspicious\s+activity", "high"),
    (r"are\s+you\s+human|verify\s+you\s+are\s+human", "high"),
    (r"automated\s+(access|request)|bot\s+detected", "critical"),
    (r"too\s+many\s+(requests|attempts)|rate\s+limit", "medium"),
    (r"access\s+denied|forbidden", "medium"),
]

_BLOCK_URL_PATTERNS = [
    (r"/captcha", "high"),
    (r"/challenge", "high"),
    (r"/blocked", "critical"),
    (r"/security/check", "high"),
    (r"/verify", "medium"),
]


def _scan_cookies(page) -> tuple[list[str], list[dict]]:
    vendors_found: list[Any] = []
    signals: list[Any] = []
    try:
        cookies = page.context.cookies()
    except Exception:  # noqa: BLE001 - 봇 탐지 신호(쿠키/DOM/응답헤더) 스캔 도구 - 스캔 실패 시 unknown/빈 목록 반환, 차단 여부를 직접 결정하지 않는 리포팅 전용
        return vendors_found, signals
    for vendor, sig in _VENDORS.items():
        for c in cookies:
            cname = c.get("name", "")
            for pat in sig["cookies"]:
                if pat in cname:
                    if vendor not in vendors_found:
                        vendors_found.append(vendor)
                    signals.append(
                        {
                            "kind": "vendor_cookie",
                            "vendor": vendor,
                            "detail": cname,
                            "severity": "medium",
                        }
                    )
                    break
    return vendors_found, signals


def _match_dom_vendors(data: dict) -> tuple[list[str], list[dict]]:
    """DOM 스캔 결과에서 벤더 스크립트/HTML 마커를 매칭."""
    vendors_found: list[str] = []
    signals: list[dict] = []

    # 벤더 스크립트 매칭
    for vendor, sig in _VENDORS.items():
        for src in data.get("scripts", []):
            for pat in sig["scripts"]:
                if pat in src:
                    if vendor not in vendors_found:
                        vendors_found.append(vendor)
                    signals.append(
                        {
                            "kind": "vendor_script",
                            "vendor": vendor,
                            "detail": src[:200],
                            "severity": "medium",
                        }
                    )
                    break
        # HTML 내 마커
        html = data.get("html_snippet", "")
        for pat in sig["html"]:
            if pat in html:
                if vendor not in vendors_found:
                    vendors_found.append(vendor)
                signals.append(
                    {
                        "kind": "vendor_html",
                        "vendor": vendor,
                        "detail": pat,
                        "severity": "low",
                    }
                )
    return vendors_found, signals


def _scan_dom(page) -> tuple[list[str], list[dict]]:
    """DOM 안의 vendor 스크립트, 차단 텍스트, CAPTCHA 위젯 탐지."""
    js = r"""
    () => {
        const scripts = Array.from(document.scripts).map(s => s.src || '').filter(Boolean);
        const html = document.documentElement ? document.documentElement.outerHTML : '';
        const text = (document.body && document.body.innerText) || '';
        // 캡차 위젯 존재
        const widgets = [];
        if (document.querySelector('.g-recaptcha, [data-sitekey]')) widgets.push('recaptcha_widget');
        if (document.querySelector('.h-captcha, .hcaptcha-box')) widgets.push('hcaptcha_widget');
        if (document.querySelector('.cf-turnstile, [data-callback*=turnstile]')) widgets.push('turnstile_widget');
        if (document.querySelector('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[src*="captcha"]')) widgets.push('captcha_iframe');
        if (document.querySelector('iframe[src*="arkoselabs"], iframe[src*="funcaptcha"]')) widgets.push('funcaptcha_iframe');
        return {scripts, html_snippet: html.slice(0, 50000), text: text.slice(0, 30000), widgets, url: location.href};
    }
    """
    try:
        data = page.evaluate(js)
    except Exception as e:  # noqa: BLE001 - 봇 탐지 신호(쿠키/DOM/응답헤더) 스캔 도구 - 스캔 실패 시 unknown/빈 목록 반환, 차단 여부를 직접 결정하지 않는 리포팅 전용
        log.debug("[bot-radar] dom scan 실패: %s", e)
        return [], []

    vendors_found, signals = _match_dom_vendors(data)

    # CAPTCHA 위젯
    for w in data.get("widgets", []):
        signals.append(
            {
                "kind": "captcha_widget",
                "detail": w,
                "severity": "critical",
            }
        )

    # 차단 텍스트
    text = data.get("text", "")
    for pat, sev in _BLOCK_TEXT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            signals.append(
                {
                    "kind": "block_text",
                    "detail": m.group(0)[:120],
                    "severity": sev,
                }
            )

    # URL 패턴
    url = data.get("url", "")
    for pat, sev in _BLOCK_URL_PATTERNS:
        if re.search(pat, url, re.IGNORECASE):
            signals.append(
                {
                    "kind": "block_url",
                    "detail": url[:200],
                    "severity": sev,
                }
            )

    return vendors_found, signals


_SEVERITY_WEIGHT = {"low": 0.1, "medium": 0.4, "high": 0.8, "critical": 1.0}


def _summarize(vendors: list[str], signals: list[dict]) -> dict:
    if not signals:
        return {
            "flagged": False,
            "confidence": 0.0,
            "level": "clean",
            "vendors": vendors,
            "signals": [],
        }
    # confidence = 1 - product(1 - w) (보수적 OR)
    p_clean = 1.0
    for s in signals:
        w = _SEVERITY_WEIGHT.get(s.get("severity", "low"), 0.1)
        p_clean *= 1 - w
    confidence = round(1 - p_clean, 3)

    has_critical = any(s.get("severity") == "critical" for s in signals)
    has_high = any(s.get("severity") == "high" for s in signals)
    has_widget = any(s.get("kind") == "captcha_widget" for s in signals)

    if has_critical or has_widget:
        level = "blocked"
    elif has_high:
        level = "challenged"
    elif vendors:
        level = "monitored"
    else:
        level = "clean"

    return {
        "flagged": level in ("blocked", "challenged"),
        "confidence": confidence,
        "level": level,
        "vendors": vendors,
        "signals": signals,
    }


# ── 공개 API ───────────────────────────────────────────────────────


def scan(page) -> dict:
    """현재 페이지 1회 스캔. 봇 감지 상태 보고."""
    vendors_a, signals_a = _scan_cookies(page)
    vendors_b, signals_b = _scan_dom(page)
    vendors = list(dict.fromkeys(vendors_a + vendors_b))
    signals = signals_a + signals_b
    result = _summarize(vendors, signals)
    log.info(
        "[bot-radar] level=%s confidence=%.2f vendors=%s signals=%d",
        result["level"],
        result["confidence"],
        vendors,
        len(signals),
    )
    return result


def assert_not_blocked(page) -> dict:
    """스캔 후 blocked/challenged 면 BotDetected 발생. 그 외엔 보고서 반환."""
    r = scan(page)
    if r["flagged"]:
        raise BotDetected(r)
    return r


class BotRadar:
    """장기 모니터링용. 이벤트 훅 + 누적 신호.

    사용:
        radar = BotRadar(page)
        radar.arm()
        ... 작업 ...
        report = radar.report()
    """

    def __init__(self, page):
        self.page = page
        self.responses: list[dict] = []
        self.requests: list[dict] = []
        self._armed = False

    def arm(self) -> None:
        if self._armed:
            return
        try:
            self.page.on("response", self._on_response)
            self.page.on("requestfailed", self._on_request_failed)
            self._armed = True
        except Exception as e:  # noqa: BLE001 - 봇 탐지 신호(쿠키/DOM/응답헤더) 스캔 도구 - 스캔 실패 시 unknown/빈 목록 반환, 차단 여부를 직접 결정하지 않는 리포팅 전용
            log.debug("[bot-radar] arm 실패: %s", e)

    def _on_response(self, resp) -> None:
        try:
            status = resp.status
            url = resp.url
            if status in (403, 429, 503):
                self.responses.append(
                    {
                        "kind": "http_block",
                        "status": status,
                        "url": url[:200],
                        "severity": "high" if status == 429 else "medium",
                    }
                )
            # 헤더 기반 vendor 식별
            try:
                headers = resp.headers
            except Exception:  # noqa: BLE001 - 봇 탐지 신호(쿠키/DOM/응답헤더) 스캔 도구 - 스캔 실패 시 unknown/빈 목록 반환, 차단 여부를 직접 결정하지 않는 리포팅 전용
                headers = {}
            for vendor, pats in [
                ("cloudflare_bot", ["cf-ray", "cf-bm", "cf-cache-status"]),
                ("akamai_bot", ["akamai-", "x-akamai"]),
                ("perimeterx", ["x-px-"]),
                ("datadome", ["x-datadome"]),
                ("imperva_incapsula", ["x-iinfo", "x-cdn"]),
            ]:
                for h in pats:
                    if any(h.lower() in (k or "").lower() for k in headers):
                        self.responses.append(
                            {
                                "kind": "vendor_header",
                                "vendor": vendor,
                                "detail": h,
                                "severity": "low",
                            }
                        )
                        break
        except Exception:  # noqa: BLE001 - 봇 탐지 신호(쿠키/DOM/응답헤더) 스캔 도구 - 스캔 실패 시 unknown/빈 목록 반환, 차단 여부를 직접 결정하지 않는 리포팅 전용
            pass

    def _on_request_failed(self, req) -> None:
        # 봇 탐지 신호 스캔 도구 - 이벤트 기록 실패는 무시(리포팅 전용, 차단 여부를 직접 결정하지 않음)
        with contextlib.suppress(Exception):
            self.requests.append(
                {
                    "kind": "request_failed",
                    "url": req.url[:200],
                    "severity": "low",
                }
            )

    def report(self) -> dict:
        # DOM/cookie 스캔 + 누적 이벤트 합산
        live = scan(self.page)
        all_signals = list(live["signals"]) + self.responses + self.requests
        vendors = list(dict.fromkeys(live["vendors"] + [s.get("vendor") for s in self.responses if s.get("vendor")]))
        return _summarize(vendors, all_signals)
