"""EUM WEBMAN381M00 device registration helper.

Default behavior prepares the form only. The final submit click is performed
only when submit=True.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time as _time
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
REGISTRATION_URL = f"{EUM_BASE}/web/man/WEBMAN381M00"
FORM_ANALYSIS_PATH = ROOT / "data" / "form_analysis.json"

PROJECT_SELECTORS = [
    "input[name*='gong']",
    "input[id*='gong']",
    "input[name*='cntr']",
    "input[id*='cntr']",
    "input[name*='biz']",
    "input[id*='biz']",
    "input[name*='site']",
    "input[id*='site']",
    "input[name*='project']",
    "input[name*='Project']",
    "[id*='project']",
    "[id*='Project']",
    "input[name*='prj']",
    "[id*='prj']",
]
DEVICE_SELECTORS = [
    "input[name*='tmn']",
    "input[id*='tmn']",
    "input[name*='term']",
    "input[id*='term']",
    "input[name*='eqp']",
    "input[id*='eqp']",
    "input[name*='device']",
    "input[name*='Device']",
    "input[name*='terminal']",
    "input[name*='terminalNo']",
    "[id*='device']",
    "[id*='terminal']",
]
LOCATION_SELECTORS = [
    "input[name*='place']",
    "textarea[name*='place']",
    "input[id*='place']",
    "textarea[id*='place']",
    "input[name*='location']",
    "textarea[name*='location']",
    "[id*='location']",
    "input[name*='addr']",
    "textarea[name*='addr']",
    "[id*='addr']",
]
DATE_SELECTORS = [
    "input[type='date']",
    "input[name*='install']",
    "input[id*='install']",
    "input[name*='instl']",
    "input[id*='instl']",
    "input[name*='date']",
    "[id*='date']",
]
SUBMIT_SELECTORS = [
    "a:has-text('등록')",
    "a:has-text('저장')",
    "a:has-text('신청')",
    "button:has-text('저장')",
    "button:has-text('등록')",
    "button:has-text('제출')",
    "button:has-text('신청')",
    "input[type='button'][value*='등록']",
    "input[type='button'][value*='저장']",
    "input[type='button'][value*='신청']",
    "button[type='submit']",
    "input[type='submit']",
    "#btnSubmit",
    ".btn-submit",
]

PROJECT_KEYWORDS = ["공사", "현장", "공제가입", "사업장", "project", "prj", "cntr", "biz", "site"]
DEVICE_KEYWORDS = ["단말기", "단말", "기기", "terminal", "device", "tmn", "term", "eqp"]
LOCATION_KEYWORDS = ["설치장소", "설치위치", "주소", "장소", "위치", "location", "addr", "place"]
DATE_KEYWORDS = ["설치일", "설치일자", "일자", "date", "install", "instl"]
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
            locator = page.locator(selector)
            if locator.count() > 0:
                page.fill(selector, value)
                _time.sleep(0.2)
                return selector
        except Exception:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            continue
    log.warning("[registration] failed to fill %s", field)
    return None


def _load_form_analysis() -> dict[str, Any]:
    """Load the latest captured form selectors when available."""
    if not FORM_ANALYSIS_PATH.exists():
        try:
            from scripts.eum.form_analyzer import main as analyze_forms

            analyze_forms()
        except Exception as exc:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            log.debug("[registration] form analysis refresh skipped: %s", exc)
    if not FORM_ANALYSIS_PATH.exists():
        return {}
    try:
        return json.loads(FORM_ANALYSIS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        log.debug("[registration] form analysis load failed: %s", exc)
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
            _time.sleep(0.2)
            return str(result)
    except Exception as exc:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        log.debug("[registration] semantic fill failed for %s: %s", field, exc)
    return None


def _fill_control(page, selectors: list[str], keywords: list[str], value: str, field: str) -> str | None:
    analyzed = _analyzed_field_selectors("WEBMAN381M00", keywords)
    merged = [*analyzed, *selectors]
    return _fill_first(page, merged, value, field) or _fill_by_keywords(page, keywords, value, field)


def _click_first(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                page.click(selector)
                _time.sleep(1)
                return selector
        except Exception:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
            continue
    return None


def _denial_reason(page) -> str | None:
    try:
        text = page.locator("body").inner_text(timeout=2000)
    except Exception:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        return None
    for marker in DENIAL_MARKERS:
        if marker in text:
            return f"page access denied: {marker}"
    return None


def _goto_form_page(page) -> None:
    """Open the registration page without waiting for long-polling/network idle."""
    page.goto(REGISTRATION_URL, wait_until="domcontentloaded", timeout=30000)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("load", timeout=5000)


def register_device(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    project_code: str,
    project_name: str,
    device_id: str,
    install_location: str,
    install_date: str | None = None,
    submit: bool = False,
    device_type: str = "smart-card",
) -> dict[str, Any]:
    """Prepare or submit an EUM device registration form."""
    result: dict[str, Any] = {
        "success": False,
        "prepared": False,
        "submitted": False,
        "project_code": project_code,
        "project_name": project_name,
        "device_id": device_id,
        "install_location": install_location,
        "install_date": install_date,
        "device_type": device_type,
        "filled": {},
        "fill_errors": [],
        "error": "",
    }

    try:
        page = get_page()
        ensure_logged_in(page)
        _goto_form_page(page)
        ensure_logged_in(page)
        _time.sleep(1)
        denial = _denial_reason(page)
        if denial:
            result["error"] = denial
            return result

        fields = [
            ("project_code", PROJECT_SELECTORS, PROJECT_KEYWORDS, project_code),
            ("device_id", DEVICE_SELECTORS, DEVICE_KEYWORDS, device_id),
            ("install_location", LOCATION_SELECTORS, LOCATION_KEYWORDS, install_location),
        ]
        if install_date:
            fields.append(("install_date", DATE_SELECTORS, DATE_KEYWORDS, install_date))

        for field, selectors, keywords, value in fields:
            selector = _fill_control(page, selectors, keywords, value, field)
            if selector:
                result["filled"][field] = selector
            elif field != "install_date":
                result["fill_errors"].append(field)

        if result["fill_errors"]:
            result["error"] = "required field fill failed: " + ", ".join(result["fill_errors"])
            log.warning("[registration] prepare failed: %s", result["error"])
            return result

        result["prepared"] = True
        if not submit:
            result["success"] = True
            log.info("[registration] prepared only, submit skipped: %s", device_id)
            return result

        clicked = _click_first(page, [*_analyzed_submit_selectors("WEBMAN381M00"), *SUBMIT_SELECTORS])
        if not clicked:
            result["error"] = "submit button not found"
            return result

        result["submitted"] = True
        result["success"] = True
        result["submit_selector"] = clicked
        return result

    except Exception as exc:  # noqa: BLE001 - EUM 단말기 설치신청 폼 자동입력(+선택적 제출) - submit 기본값 False, 실패시 result.error 기록하고 success=False 유지(fail-closed)
        result["error"] = str(exc)
        log.error("[registration] error: %s", exc)
        return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="EUM device registration")
    parser.add_argument("project_code", nargs="?", default="TEST-PROJECT")
    parser.add_argument("device_id", nargs="?", default="TEST-DEVICE")
    parser.add_argument("location", nargs="?", default="TEST-LOCATION")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    if args.submit:
        gate_check("eum_register_device", context="EUM device registration")

    result = register_device(
        args.project_code,
        args.project_code,
        args.device_id,
        args.location,
        submit=args.submit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
