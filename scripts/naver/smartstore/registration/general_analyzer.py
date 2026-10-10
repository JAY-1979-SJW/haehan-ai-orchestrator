"""일반 상품 등록 페이지 (필드 248개) 정밀 분석.

URL: https://sell.smartstore.naver.com/#/products/edit-new

목적: 가격/재고/판매옵션/배송 필드의 정확한 셀렉터 추출 → GeneralProductRegister 구축.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402

URL = "https://sell.smartstore.naver.com/#/products/edit-new"
OUTPUT = ROOT / "data" / "sitemap" / "smartstore_general_product_fields.json"


EXTRACT_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const findContextLabel = (el) => {
        let parent = el.parentElement;
        for (let i = 0; i < 6 && parent; i++) {
            // 라벨 형제
            const sib = parent.previousElementSibling;
            if (sib) {
                const t = (sib.innerText || '').trim();
                if (t && t.length >= 1 && t.length < 30) return t;
            }
            // 부모 내 label
            const lbl = parent.querySelector(':scope > label, :scope > .label, :scope > dt');
            if (lbl && lbl !== el) {
                const t = (lbl.innerText || '').trim();
                if (t && t.length < 30) return t;
            }
            parent = parent.parentElement;
        }
        return '';
    };

    const fields = [];
    const seen = new Set();
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        const name = el.name || '';
        const id = el.id || '';
        const key = `${type}|${name}|${id}|${el.placeholder || ''}`;
        if (seen.has(key)) return;
        seen.add(key);

        const r = el.getBoundingClientRect();
        const label = el.getAttribute('aria-label') || el.placeholder || findContextLabel(el);
        fields.push({
            type, name, id,
            placeholder: el.placeholder || '',
            aria_label: el.getAttribute('aria-label') || '',
            context_label: label.substring(0, 50),
            required: el.required || el.getAttribute('aria-required') === 'true',
            cls: (el.className || '').substring(0, 50),
            position: {x: Math.round(r.x), y: Math.round(r.y + window.scrollY)},
        });
    });

    // 섹션 헤더
    const sections = [];
    document.querySelectorAll('h1, h2, h3, h4, [class*="section-title"], [class*="SectionTitle"], legend').forEach(s => {
        if (!isVisible(s)) return;
        const text = (s.innerText || '').trim();
        if (!text || text.length < 2 || text.length > 60) return;
        const r = s.getBoundingClientRect();
        sections.push({text, y: Math.round(r.y + window.scrollY)});
    });

    return {
        url: location.href,
        page_height: document.body.scrollHeight,
        field_count: fields.length,
        fields: fields,
        sections: sections,
    };
}
"""


def _open_analyzer_page(page) -> None:
    """분석 페이지 진입 + 팝업 처리."""
    page.goto(URL, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        pass


def _scroll_collect(page):
    """페이지 전체 스크롤하며 필드/섹션 수집."""
    # 페이지 전체 스크롤 (동적 필드 로드 보장)
    all_fields = {}
    all_sections = {}
    for y in range(0, 15000, 600):
        page.evaluate(f"window.scrollTo(0, {y})")
        time.sleep(0.7)
        snap = page.evaluate(EXTRACT_JS)
        for f in snap.get("fields", []):
            key = f"{f['type']}|{f['name']}|{f['id']}|{f['placeholder']}"
            if key not in all_fields:
                all_fields[key] = f
        for s in snap.get("sections", []):
            all_sections[s["text"]] = s
        if y >= snap.get("page_height", 0):
            break
    return all_fields, all_sections


def _classify_fields(all_fields):
    """핵심 필드 분류."""
    # 핵심 필드 추출 (가격/재고/배송/옵션 관련)
    keywords = {
        "price": ["가격", "판매가", "price", "salePrice", "원"],
        "stock": ["재고", "수량", "stock", "quantity"],
        "delivery": ["배송", "delivery", "shipping"],
        "option": ["옵션", "option"],
        "name": ["상품명", "product.name", "title"],
        "category": ["카테고리", "category"],
    }

    by_keyword = {k: [] for k in keywords}
    for f in all_fields.values():
        text = f["name"] + " " + f["placeholder"] + " " + f["context_label"] + " " + f["aria_label"]
        text_lower = text.lower()
        for kw, terms in keywords.items():
            if any(t.lower() in text_lower for t in terms):
                by_keyword[kw].append(f)
                break
    return by_keyword


def _report(by_keyword, all_sections) -> None:
    """분류 결과 보고."""
    # 보고
    print("\n  [핵심 필드 분류]")
    for kw, items in by_keyword.items():
        print(f"    {kw}: {len(items)}개")
        for f in items[:3]:
            print(
                f"      - {f['type']:<10} name={f['name'][:25]:<27} placeholder='{f['placeholder'][:30]}' label='{f['context_label'][:30]}'"
            )

    print(f"\n  [섹션 헤더 ({len(all_sections)}개)]")
    for s in sorted(all_sections.values(), key=lambda x: x["y"])[:40]:
        print(f"     y={s['y']:>5}  {s['text']}")

    print(f"\n  ✓ 저장: {OUTPUT.name}")


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  일반 상품 등록 페이지 (필드 248개) 정밀 분석")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    _open_analyzer_page(page)

    print(f"  ✓ 진입: {page.url}")
    print("  페이지 스크롤하며 필드 수집...")

    all_fields, all_sections = _scroll_collect(page)

    print(f"  총 필드: {len(all_fields)}, 섹션: {len(all_sections)}")

    by_keyword = _classify_fields(all_fields)

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "url": URL,
                "total_fields": len(all_fields),
                "sections": sorted(all_sections.values(), key=lambda x: x["y"]),
                "by_keyword": by_keyword,
                "all_fields": sorted(all_fields.values(), key=lambda x: x["position"]["y"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _report(by_keyword, all_sections)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        import traceback

        traceback.print_exc()
