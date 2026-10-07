"""상품 등록 페이지 전체 필드 정밀 분석 (스크롤 포함).

ProductRegister 모듈 구축 전, 페이지의 모든 입력 필드/버튼/라디오/체크박스를
스크롤하며 추출. 결과를 JSON으로 저장.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.auth.login_detector import is_logged_in_generic  # noqa: E402
from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402

_log = get_logger(__name__)

PRODUCT_REGISTER_URL = "https://sell.smartstore.naver.com/#/products/standard-group-product/create"
OUTPUT = ROOT / "data" / "sitemap" / "smartstore_product_register_fields.json"


EXTRACT_ALL_FIELDS_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const cssEsc = (s) => window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, '\\$&');

    const sel = (el) => {
        if (!el) return null;
        if (el.id) return '#' + cssEsc(el.id);
        if (el.name) return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        const cls = (el.className || '').toString().trim().split(/\s+/).filter(Boolean);
        if (cls.length) return el.tagName.toLowerCase() + '.' + cls.slice(0, 2).map(cssEsc).join('.');
        return el.tagName.toLowerCase();
    };

    const findLabel = (el) => {
        // 1. aria-label
        let l = el.getAttribute('aria-label') || el.placeholder || '';
        if (l) return l;
        // 2. label[for=id]
        if (el.id) {
            const lbl = document.querySelector(`label[for="${el.id}"]`);
            if (lbl) return (lbl.innerText || '').trim();
        }
        // 3. 부모의 label 또는 .label
        let parent = el.parentElement;
        for (let i = 0; i < 5 && parent; i++) {
            const lbl = parent.querySelector('label, .label, [class*="label"], [class*="title"]');
            if (lbl && lbl !== el) {
                const txt = (lbl.innerText || '').trim();
                if (txt && txt.length < 80) return txt;
            }
            // 형제 텍스트
            const prev = parent.previousElementSibling;
            if (prev) {
                const t = (prev.innerText || '').trim();
                if (t && t.length < 80) return t;
            }
            parent = parent.parentElement;
        }
        return '';
    };

    const fields = [];
    const seenSelectors = new Set();
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        const selector = sel(el);
        // 중복 방지
        const key = `${selector}|${type}|${el.name||''}`;
        if (seenSelectors.has(key)) return;
        seenSelectors.add(key);

        const r = el.getBoundingClientRect();
        fields.push({
            type: type,
            selector: selector,
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            value: el.value || '',
            required: el.required || el.getAttribute('aria-required') === 'true',
            disabled: el.disabled,
            label: findLabel(el),
            position: { x: Math.round(r.x), y: Math.round(r.y + window.scrollY) },
            cls: (el.className || '').substring(0, 80),
        });
    });

    // 모든 버튼
    const buttons = [];
    const seenBtn = new Set();
    document.querySelectorAll('button, a.btn, a[role=button], [class*="button"]').forEach(b => {
        if (!isVisible(b)) return;
        const text = (b.innerText || '').trim();
        if (!text || text.length < 1 || text.length > 40) return;
        const key = text + '|' + (b.className || '').substring(0, 20);
        if (seenBtn.has(key)) return;
        seenBtn.add(key);
        const r = b.getBoundingClientRect();
        buttons.push({
            text: text,
            tag: b.tagName,
            cls: (b.className || '').substring(0, 80),
            position: { x: Math.round(r.x), y: Math.round(r.y + window.scrollY) },
        });
    });

    // 섹션 헤더 (h1/h2/h3/.title 등)
    const sections = [];
    document.querySelectorAll('h1, h2, h3, h4, [class*="section-title"], [class*="SectionTitle"]').forEach(s => {
        if (!isVisible(s)) return;
        const text = (s.innerText || '').trim();
        if (!text || text.length > 60) return;
        const r = s.getBoundingClientRect();
        sections.push({text, y: Math.round(r.y + window.scrollY)});
    });

    return {
        url: location.href,
        title: document.title,
        page_height: document.body.scrollHeight,
        viewport: { w: window.innerWidth, h: window.innerHeight },
        fields_count: fields.length,
        fields: fields,
        buttons: buttons,
        sections: sections,
    };
}
"""


def scroll_and_collect(page, max_scrolls: int = 30, scroll_step: int = 600) -> dict:
    """페이지를 천천히 스크롤하며 동적 로드되는 필드까지 모두 수집."""
    all_fields = {}
    all_buttons = {}
    all_sections = {}

    for i in range(max_scrolls):
        # 데이터 수집
        snapshot = page.evaluate(EXTRACT_ALL_FIELDS_JS)
        for f in snapshot.get("fields", []):
            key = f["selector"] + "|" + f["type"] + "|" + f["name"]
            if key not in all_fields:
                all_fields[key] = f
        for b in snapshot.get("buttons", []):
            key = b["text"] + "|" + b["cls"][:30]
            if key not in all_buttons:
                all_buttons[key] = b
        for s in snapshot.get("sections", []):
            all_sections[s["text"]] = s

        # 페이지 끝까지 스크롤했는지 확인
        current_pos = page.evaluate("() => window.scrollY")
        page_height = snapshot.get("page_height", 0)
        viewport_h = snapshot.get("viewport", {}).get("h", 800)

        print(
            f"  [scroll {i + 1}/{max_scrolls}] y={current_pos:>5} / {page_height} | 필드 {len(all_fields)} 버튼 {len(all_buttons)} 섹션 {len(all_sections)}",
            flush=True,
        )

        if current_pos + viewport_h >= page_height - 50:
            print("  ✓ 페이지 끝 도달")
            break

        # 스크롤
        page.evaluate(f"window.scrollTo(0, {current_pos + scroll_step})")
        time.sleep(0.8)

    return {
        "url": snapshot.get("url", ""),
        "title": snapshot.get("title", ""),
        "page_height": snapshot.get("page_height", 0),
        "fields": sorted(all_fields.values(), key=lambda x: x["position"]["y"]),
        "buttons": sorted(all_buttons.values(), key=lambda x: x["position"]["y"]),
        "sections": sorted(all_sections.values(), key=lambda x: x["y"]),
    }


def main():
    print(f"\n{'=' * 70}")
    print("  상품 등록 페이지 전체 필드 정밀 분석")
    print(f"{'=' * 70}\n")

    page = get_page()

    # 로그인 확인
    r = ensure_naver_login(page)
    if not r.get("ok"):
        print(f"  ✗ 로그인 실패: {r.get('reason')}")
        sys.exit(1)

    # 등록 페이지 진입
    print(f"  [1] 등록 페이지 진입: {PRODUCT_REGISTER_URL}")
    page.goto(PRODUCT_REGISTER_URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력 후 sys.exit(1)로 명시적 실패 종료
        pass

    if not is_logged_in_generic(page):
        print("  ✗ 로그인 인증 실패")
        sys.exit(1)

    print(f"  ✓ 진입 성공: {page.url}")

    # 스크롤하며 전체 수집
    print("\n  [2] 페이지 스크롤하며 모든 필드 수집")
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)
    result = scroll_and_collect(page, max_scrolls=30, scroll_step=600)

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n  [3] 최종 결과")
    print(f"     필드: {len(result['fields'])}개")
    print(f"     버튼: {len(result['buttons'])}개")
    print(f"     섹션: {len(result['sections'])}개")
    print(f"     저장: {OUTPUT.name}")

    # 섹션 출력
    print("\n  [섹션 헤더]")
    for s in result["sections"][:30]:
        print(f"     y={s['y']:>5}  {s['text']}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력 후 sys.exit(1)로 명시적 실패 종료
        import traceback

        traceback.print_exc()
        sys.exit(1)
