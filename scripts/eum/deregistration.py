"""EUM WEBMAN382M00 device deregistration/removal helper.

Default behavior prepares the form only. The final submit click is performed
only when submit=True.
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from scripts.eum.auth import ensure_logged_in
from scripts.common.gate import check as gate_check  # noqa: E402 - sys.path 부트스트랩 뒤 import
from scripts.common.logger import get_logger  # noqa: E402 - sys.path 부트스트랩 뒤 import
from scripts.browser.cdp.connection import get_page  # noqa: E402 - sys.path 부트스트랩 뒤 import(이동 전부터 있던 패턴)

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"
DEREGISTRATION_URL = f"{EUM_BASE}/web/man/WEBMAN382M00"
FORM_ANALYSIS_PATH = ROOT / "data" / "form_analysis.json"

DEVICE_SELECTORS = [
    "input[name*='tmn']",
    "input[id*='tmn']",
    "input[name*='term']",
    "input[id*='term']",
    "input[name*='eqp']",
    "input[id*='eqp']",
    "input[name*='device']",
    "input[name*='Device']",
    "input[name*='terminalNo']",
    "input[name*='terminal']",
    "[id*='device']",
    "[id*='terminal']",
]
DATE_SELECTORS = [
    "input[type='date']",
    "input[name*='remove']",
    "input[id*='remove']",
    "input[name*='dereg']",
    "input[id*='dereg']",
    "input[name*='del']",
    "input[id*='del']",
    "input[name*='date']",
    "[id*='date']",
]
SUBMIT_SELECTORS = [
    "a:has-text('철거')",
    "a:has-text('말소')",
    "a:has-text('저장')",
    "a:has-text('신청')",
    "button:has-text('철거')",
    "button:has-text('말소')",
    "button:has-text('저장')",
    "button:has-text('신청')",
    "button:has-text('제출')",
    "input[type='button'][value*='철거']",
    "input[type='button'][value*='말소']",
    "input[type='button'][value*='저장']",
    "input[type='button'][value*='신청']",
    "button[type='submit']",
    "input[type='submit']",
    "#btnSubmit",
    ".btn-submit",
]

DEVICE_KEYWORDS = ["단말기", "단말", "기기", "terminal", "device", "tmn", "term", "eqp"]
DATE_KEYWORDS = ["철거일", "말소일", "철거예정", "일자", "date", "remove", "dereg", "delete", "del"]
DENIAL_MARKERS = [
    "접근 권한",
    "권한이 없습니다",
    "권한이 존재하지",
    "접근할 수 없습니다",
    "이용 권한",
    "사용 권한",
    "허용되지",
]


def _fill_first(page, selectors: list[str], value: str, field: str) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                page.fill(selector, value)
                time.sleep(0.2)
                return selector
        except Exception:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            continue
    log.warning("[deregistration] failed to fill %s", field)
    return None


def _load_form_analysis() -> dict[str, Any]:
    """Load the latest captured form selectors when available."""
    if not FORM_ANALYSIS_PATH.exists():
        try:
            from scripts.eum.form_analyzer import main as analyze_forms

            analyze_forms()
        except Exception as exc:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            log.debug("[deregistration] form analysis refresh skipped: %s", exc)
    if not FORM_ANALYSIS_PATH.exists():
        return {}
    try:
        return json.loads(FORM_ANALYSIS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        log.debug("[deregistration] form analysis load failed: %s", exc)
        return {}


# form_selectors 는 함수 안에서 import 한다(이 파일의 모듈 import 는 sys.path 부트스트랩 뒤라 상단에 추가하면 E402).
def _analysis_entries(page_code: str) -> list[dict[str, Any]]:
    from scripts.eum.form_selectors import analysis_entries

    return analysis_entries(_load_form_analysis(), page_code)


def _analyzed_field_selectors(page_code: str, keywords: list[str]) -> list[str]:
    from scripts.eum.form_selectors import field_selectors

    return field_selectors(_analysis_entries(page_code), keywords)


def _analyzed_submit_selectors(page_code: str) -> list[str]:
    from scripts.eum.form_selectors import submit_selectors

    return submit_selectors(_analysis_entries(page_code))


def _fill_by_keywords(page, keywords: list[str], value: str, field: str) -> str | None:
    """Fill the best visible input/textarea matched by nearby Korean/English labels."""
    try:
        result = page.evaluate(
            """({keywords, value}) => {
                const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 &&
                        style.display !== 'none' && style.visibility !== 'hidden';
                };
                const cssPath = (el) => {
                    if (el.id) return `#${CSS.escape(el.id)}`;
                    if (el.name) return `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`;
                    const all = Array.from(document.querySelectorAll(el.tagName.toLowerCase()));
                    return `${el.tagName.toLowerCase()}:nth-of-type(${all.indexOf(el) + 1})`;
                };
                const labelText = (el) => {
                    const parts = [
                        el.id, el.name, el.placeholder, el.title,
                        el.getAttribute('aria-label'), el.getAttribute('data-name'),
                    ];
                    if (el.id) {
                        const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                        if (label) parts.push(label.innerText || label.textContent || '');
                    }
                    let node = el;
                    for (let i = 0; node && i < 4; i += 1, node = node.parentElement) {
                        parts.push(node.innerText || node.textContent || '');
                    }
                    return norm(parts.join(' '));
                };
                const keys = keywords.map(norm).filter(Boolean);
                const candidates = Array.from(document.querySelectorAll(
                    'input:not([type=hidden]), textarea'
                )).filter((el) => !el.disabled && !el.readOnly && visible(el));
                const scored = candidates.map((el, index) => {
                    const text = labelText(el);
                    const score = keys.reduce((sum, key) => sum + (text.includes(key) ? 1 : 0), 0);
                    return { el, index, score, text };
                }).filter((row) => row.score > 0)
                  .sort((a, b) => b.score - a.score || a.index - b.index);
                if (!scored.length) return null;
                const el = scored[0].el;
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return cssPath(el);
            }""",
            {"keywords": keywords, "value": value},
        )
        if result:
            time.sleep(0.2)
            return str(result)
    except Exception as exc:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        log.debug("[deregistration] semantic fill failed for %s: %s", field, exc)
    return None


def _fill_control(page, selectors: list[str], keywords: list[str], value: str, field: str) -> str | None:
    analyzed = _analyzed_field_selectors("WEBMAN382M00", keywords)
    merged = [*analyzed, *selectors]
    return _fill_first(page, merged, value, field) or _fill_by_keywords(page, keywords, value, field)


def _click_first(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                page.click(selector)
                time.sleep(1)
                return selector
        except Exception:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            continue
    return None


def _denial_reason(page) -> str | None:
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except Exception:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        return None
    for marker in DENIAL_MARKERS:
        if marker in text:
            return f"page access denied: {marker}"
    return None


def _goto_form_page(page) -> None:
    """Open the deregistration page without waiting for long-polling/network idle."""
    page.goto(DEREGISTRATION_URL, wait_until="domcontentloaded", timeout=30000)
    with suppress(Exception):
        page.wait_for_load_state("load", timeout=5000)


def deregister_device(device_id: str, deregister_date: str | None = None, submit: bool = False) -> dict[str, Any]:
    """Prepare or submit an EUM device deregistration/removal form."""
    result: dict[str, Any] = {
        "success": False,
        "prepared": False,
        "submitted": False,
        "device_id": device_id,
        "deregister_date": deregister_date,
        "filled": {},
        "fill_errors": [],
        "error": "",
    }

    try:
        page = get_page()
        ensure_logged_in(page)
        _goto_form_page(page)
        ensure_logged_in(page)
        time.sleep(1)
        denial = _denial_reason(page)
        if denial:
            result["error"] = denial
            return result

        device_selector = _fill_control(page, DEVICE_SELECTORS, DEVICE_KEYWORDS, device_id, "device_id")
        if device_selector:
            result["filled"]["device_id"] = device_selector
        else:
            result["fill_errors"].append("device_id")

        if deregister_date:
            date_selector = _fill_control(page, DATE_SELECTORS, DATE_KEYWORDS, deregister_date, "deregister_date")
            if date_selector:
                result["filled"]["deregister_date"] = date_selector

        if result["fill_errors"]:
            result["error"] = "required field fill failed: " + ", ".join(result["fill_errors"])
            log.warning("[deregistration] prepare failed: %s", result["error"])
            return result

        result["prepared"] = True
        if not submit:
            result["success"] = True
            log.info("[deregistration] prepared only, submit skipped: %s", device_id)
            return result

        clicked = _click_first(page, [*_analyzed_submit_selectors("WEBMAN382M00"), *SUBMIT_SELECTORS])
        if not clicked:
            result["error"] = "submit button not found"
            return result

        result["submitted"] = True
        result["success"] = True
        result["submit_selector"] = clicked
        return result

    except Exception as exc:  # noqa: BLE001 - EUM 단말기 철거신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        result["error"] = str(exc)
        log.error("[deregistration] error: %s", exc)
        return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="EUM device deregistration")
    parser.add_argument("device_id", nargs="?", default="TEST-DEVICE")
    parser.add_argument("date", nargs="?")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    if args.submit:
        gate_check("eum_deregister_device", context="EUM device deregistration")

    result = deregister_device(args.device_id, args.date, submit=args.submit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
