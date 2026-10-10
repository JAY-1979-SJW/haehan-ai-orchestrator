"""일반 상품 등록 페이지 URL 자동 발견.

그룹상품 외의 진짜 '상품 등록' 페이지를 찾기 위해 여러 URL 후보 시도.
성공 시: 페이지 메타 + 가격/재고 필드 존재 여부 보고.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import handle_page_popups  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402

BASE = "https://sell.smartstore.naver.com"

# 일반 상품 등록 페이지 후보 URL들
CANDIDATES = [
    "/#/products/edit-new",
    "/#/products/new",
    "/#/products/create",
    "/#/product/new",
    "/#/product/create",
    "/#/product/sell",
    "/#/products/edit",
    "/#/sales/product/new",
    "/#/sales/product/create",
    "/#/standard-product/create",
    "/#/normal-product/create",
    "/#/products/register",
    "/#/regProduct",
    "/#/seller/products/new",
]

OUTPUT = ROOT / "data" / "sitemap" / "smartstore_register_url_search.json"


def analyze_page(page) -> dict:
    """현재 페이지 분석 — 가격/재고 필드 존재 여부."""
    return page.evaluate("""
    () => {
        const txt = (document.body?.innerText || '').toLowerCase();
        const result = {
            url: location.href,
            title: document.title,
            heading: document.querySelector('h1, h2, [class*="title"]')?.innerText?.trim().substring(0, 100) || '',
            has_price: /판매가|가격|price/i.test(txt),
            has_stock: /재고|수량|stock/i.test(txt),
            has_option: /판매옵션|옵션|option/i.test(txt),
            has_delivery: /배송|delivery/i.test(txt),
            is_error: /유효하지\\s*않|접근\\s*권한|access\\s*denied|404|페이지\\s*요청\\s*오류/i.test(txt),
            redirect_to: location.href.includes('error') || location.href.includes('login') ? location.href : '',
            field_count: document.querySelectorAll('input, select, textarea').length,
            // 가격 input 검색
            price_inputs: Array.from(document.querySelectorAll('input')).filter(i => {
                const t = (i.placeholder || '').toLowerCase() + ' ' + (i.getAttribute('aria-label') || '').toLowerCase();
                return /가격|판매가|price/.test(t) || /price|salePrice|sellPrice/i.test(i.name || '');
            }).map(i => ({name: i.name, placeholder: i.placeholder})),
            stock_inputs: Array.from(document.querySelectorAll('input')).filter(i => {
                const t = (i.placeholder || '').toLowerCase() + ' ' + (i.getAttribute('aria-label') || '').toLowerCase();
                return /재고|수량|stock/.test(t) || /stock|quantity/i.test(i.name || '');
            }).map(i => ({name: i.name, placeholder: i.placeholder})),
        };
        return result;
    }
    """)


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  일반 상품 등록 페이지 URL 탐색")
    print(f"  후보 {len(CANDIDATES)}개")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    results = []
    success = []
    for i, suffix in enumerate(CANDIDATES, 1):
        url = BASE + suffix
        print(f"  [{i:2}/{len(CANDIDATES)}] {suffix}", end=" ", flush=True)
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            time.sleep(4)
            # 팝업처리 실패 무시(읽기전용 탐색, 개별 후보 실패는 결과 목록에 에러로 기록)
            with contextlib.suppress(Exception):
                handle_page_popups(page, timeout_s=1.5)
            info = analyze_page(page)
            info["candidate"] = suffix
            results.append(info)

            if info.get("is_error") or "error" in info.get("url", "").lower():
                print("  ✗ 오류 페이지")
            elif info.get("has_price") and info.get("has_stock"):
                print(f"  ★ 가격+재고 발견! 필드 {info['field_count']}, h='{info['heading'][:30]}'")
                success.append(info)
            elif info.get("has_price") or info.get("has_stock"):
                print(f"  △ 부분 매칭 (price={info['has_price']}, stock={info['has_stock']})")
            else:
                redirected = info["url"] != url
                print(f"  · 필드 {info['field_count']}, redirect={redirected}")
        except Exception as e:  # noqa: BLE001 - 스마트스토어 상품등록 URL 후보 탐색 스크립트(읽기전용) — 팝업처리 실패 무시, 개별 후보 URL 실패는 결과 목록에 에러로 기록하고 다음 후보 계속 시도
            print(f"  ✗ {str(e)[:40]}")
            results.append({"candidate": suffix, "error": str(e)[:100]})

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "candidates_tried": len(CANDIDATES),
                "success_count": len(success),
                "success_urls": [s["candidate"] for s in success],
                "all_results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{'=' * 70}")
    print(f"  결과: 성공 {len(success)}개")
    for s in success:
        print(f"    ★ {s['candidate']} → {s['url']}")
        print(f"       제목: {s['heading'][:50]}")
        print(f"       가격 input: {s['price_inputs']}")
        print(f"       재고 input: {s['stock_inputs']}")
    print(f"\n  저장: {OUTPUT.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 스마트스토어 상품등록 URL 후보 탐색 스크립트(읽기전용) — 팝업처리 실패 무시, 개별 후보 URL 실패는 결과 목록에 에러로 기록하고 다음 후보 계속 시도
        import traceback

        traceback.print_exc()
