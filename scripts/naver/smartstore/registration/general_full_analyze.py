"""일반 상품 등록 페이지 (사이드바 클릭으로 진입) 전체 필드 정밀 분석.

흐름:
  1. 사이드바 '상품관리' → '상품 등록' 자동 클릭 진입
  2. 페이지 전체 스크롤하며 모든 필드 수집
  3. 가격/재고/배송/판매옵션 핵심 필드 셀렉터 매핑
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

DASHBOARD = "https://sell.smartstore.naver.com/#/home/dashboard"
OUTPUT = ROOT / "data" / "sitemap" / "smartstore_general_full_fields.json"


def click_text_by_coord(page, text: str, x_max: int = 280) -> bool:
    """텍스트로 메뉴 좌표 찾아 실제 마우스 클릭."""
    coords = page.evaluate(
        r"""
    ({text, xMax}) => {
        for (const el of document.querySelectorAll('a, li, button, span')) {
            const s = window.getComputedStyle(el);
            if (s.display === 'none') continue;
            const t = (el.innerText || '').trim();
            if (t === text) {
                const r = el.getBoundingClientRect();
                if (r.x < xMax && r.y > 0 && r.width > 0) {
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
        }
        return null;
    }
    """,
        {"text": text, "xMax": x_max},
    )
    if not coords:
        return False
    page.mouse.move(coords["x"], coords["y"])
    time.sleep(0.4)
    page.mouse.click(coords["x"], coords["y"])
    time.sleep(2)
    return True


EXTRACT_FIELDS_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const findLabel = (el) => {
        let l = el.getAttribute('aria-label') || el.placeholder || '';
        if (l) return l.substring(0, 50);
        if (el.id) {
            const lbl = document.querySelector(`label[for="${el.id}"]`);
            if (lbl) return (lbl.innerText || '').trim().substring(0, 50);
        }
        let parent = el.parentElement;
        for (let i = 0; i < 5 && parent; i++) {
            const sib = parent.previousElementSibling;
            if (sib) {
                const t = (sib.innerText || '').trim();
                if (t && t.length < 50) return t;
            }
            const lbl = parent.querySelector(':scope > label, :scope > .label, :scope > dt');
            if (lbl && lbl !== el) {
                const t = (lbl.innerText || '').trim();
                if (t && t.length < 50) return t;
            }
            parent = parent.parentElement;
        }
        return '';
    };

    const fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        const r = el.getBoundingClientRect();
        fields.push({
            type,
            name: el.name || '',
            id: el.id || '',
            placeholder: el.placeholder || '',
            label: findLabel(el),
            required: el.required || el.getAttribute('aria-required') === 'true',
            y: Math.round(r.y + window.scrollY),
        });
    });
    fields.sort((a, b) => a.y - b.y);

    return {url: location.href, field_count: fields.length, fields};
}
"""


def _enter_dashboard(page) -> None:
    """대시보드 진입 + 팝업 처리."""
    print("[1] 대시보드 진입")
    page.goto(DASHBOARD, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        pass


def _open_register_page(page) -> bool:
    """'상품관리' → '상품 등록' 클릭. 실패 시 False."""
    print("[2] '상품관리' 클릭")
    if not click_text_by_coord(page, "상품관리"):
        print("  ✗ 실패")
        return False

    print("[3] '상품 등록' 클릭")
    if not click_text_by_coord(page, "상품 등록"):
        print("  ✗ 실패")
        return False
    time.sleep(4)  # 동적 페이지 로드 대기
    return True


def _collect_fields(page):
    """페이지 전체 스크롤하며 필드 수집."""
    print("[4] 페이지 전체 스크롤하며 필드 수집")
    all_fields = {}
    for y in range(0, 15000, 500):
        page.evaluate(f"window.scrollTo(0, {y})")
        time.sleep(0.5)
        snap = page.evaluate(EXTRACT_FIELDS_JS)
        for f in snap["fields"]:
            key = f"{f['type']}|{f['name']}|{f['id']}"
            if key not in all_fields:
                all_fields[key] = f
        # 페이지 끝 검사
        end = page.evaluate("() => window.scrollY + window.innerHeight >= document.body.scrollHeight - 50")
        if end:
            print(f"    페이지 끝 도달 (y={y})")
            break
    return all_fields


def _classify_by_keyword(all_fields):
    """핵심 필드 분류."""
    # 핵심 필드 분류
    keywords = {
        "price": ["salePrice", "sellPrice", "originalPrice", "원가", "판매가"],
        "stock": ["stockQuantity", "stock", "재고", "수량"],
        "delivery": ["delivery", "shipping", "배송", "택배"],
        "discount": ["discount", "할인"],
        "option": ["option", "옵션"],
        "name": ["product.name", "상품명", "title", "productName"],
        "category": ["category", "카테고리"],
        "image": ["image", "이미지", "photo", "thumbnail"],
        "model": ["model", "modelName", "모델"],
        "brand": ["brand", "brandName", "브랜드"],
    }

    by_kw = {k: [] for k in keywords}
    for f in all_fields.values():
        text = (f["name"] + " " + f["placeholder"] + " " + f["label"] + " " + f["id"]).lower()
        for kw, terms in keywords.items():
            if any(t.lower() in text for t in terms):
                by_kw[kw].append(f)
                break
    return by_kw


def _report_classified(by_kw) -> None:
    """분류 결과 출력."""
    print("\n  [핵심 필드 분류]")
    for kw, items in by_kw.items():
        if not items:
            continue
        print(f"    {kw} ({len(items)}개):")
        for f in items[:5]:
            print(
                f"      - {f['type']:<10} name={f['name'][:30]:<32} placeholder='{f['placeholder'][:25]}' label='{f['label'][:25]}'"
            )


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  일반 상품 등록 페이지 전체 필드 정밀 분석")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        return

    _enter_dashboard(page)

    if not _open_register_page(page):
        return

    all_fields = _collect_fields(page)

    print(f"  총 필드: {len(all_fields)}")

    by_kw = _classify_by_keyword(all_fields)

    _report_classified(by_kw)

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "url": page.url,
                "field_count": len(all_fields),
                "all_fields": sorted(all_fields.values(), key=lambda x: x["y"]),
                "by_keyword": by_kw,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  ✓ 저장: {OUTPUT.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        import traceback

        traceback.print_exc()
