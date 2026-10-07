"""일반 상품 등록 페이지 URL 재탐색 v2.

- 추가 URL 후보 시도
- 사이드바 hover로 '상품 관리' 메뉴 펼침 → 하위 클릭
- 또는 메인 페이지 URL 직접 GET
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

# 일반 상품 등록 추가 URL 후보
CANDIDATES_V2 = [
    "/#/products/wholeProductList",
    "/#/products/wholeProduct/list",
    "/#/products/list",
    "/#/products/regular/create",
    "/#/products/general/create",
    "/#/products/single/create",
    "/#/products/single-product/create",
    "/#/products/normal/create",
    "/#/products",
    "/#/product",
    "/#/products/wholesale",
    "/#/products/individual-product/create",
    "/#/product-list",
    "/#/seller/product/new",
    "/#/seller/products",
    "/#/inventory",
    "/#/inventory/list",
    "/#/manage/products",
]


def analyze(page) -> dict:
    return page.evaluate("""
    () => {
        const txt = (document.body?.innerText || '').toLowerCase();
        return {
            url: location.href,
            title: document.title,
            heading: document.querySelector('h1, h2, [class*="title"]')?.innerText?.trim().substring(0, 100) || '',
            field_count: document.querySelectorAll('input:not([type=hidden]), select, textarea').length,
            is_group_product: location.href.includes('standard-group-product'),
            is_error: /유효하지\\s*않|접근\\s*권한|404|페이지\\s*요청\\s*오류/i.test(txt),
            // 가격/재고 input 정확히 검사
            price_input: !!document.querySelector('input[name*="salePrice"], input[name*="price"]:not([name*="settle"])'),
            stock_input: !!document.querySelector('input[name*="stockQuantity"], input[name*="stock"]'),
        };
    }
    """)


def try_sidebar_hover(page) -> dict:
    """사이드바 '상품 관리' 메뉴에 hover → 펼친 후 '상품 등록' 클릭."""
    try:
        # 대시보드로
        page.goto(f"{BASE}/#/home/dashboard", timeout=15000, wait_until="domcontentloaded")
        time.sleep(4)
        # 상품등록 페이지 URL 탐색(읽기전용 리서치) — 팝업 무시 실패해도 결과에 기록하고 계속 진행, 실제 등록 동작 없음
        with contextlib.suppress(Exception):
            handle_page_popups(page, timeout_s=1.5)

        # '상품관리' 메뉴 hover (펼침 시도)
        # 텍스트의 좌표 찾기
        coord = page.evaluate("""
        () => {
            const els = document.querySelectorAll('li, a, button');
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (t === '상품관리') {
                    const r = el.getBoundingClientRect();
                    if (r.x < 280 && r.y > 100) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
            }
            return null;
        }
        """)
        if not coord:
            return {"ok": False, "reason": "menu_not_found"}

        # hover (실제 마우스 이동)
        page.mouse.move(coord["x"], coord["y"])
        time.sleep(2)  # 펼침 애니메이션 대기

        # 펼친 후 새로 보이는 메뉴 추출
        new_menus = page.evaluate(r"""
        () => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll('a, li, button').forEach(el => {
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return;
                const r = el.getBoundingClientRect();
                if (r.width === 0) return;
                if (r.x < 5 || r.x > 280) return;
                if (r.y < 100) return;
                const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
                if (!t || t.length < 2 || t.length > 25 || seen.has(t)) return;
                if (['검색하기','상품관리','판매관리','정산관리','문의/리뷰관리','스토어관리','혜택/마케팅','N배송 관리','커머스솔루션','데이터분석','광고관리','프로모션 관리','쇼핑 커넥트','판매자 정보','온라인 교육','쇼핑 라이브 교육','정책지원금','빠른정산','사업자 대출','사업자 보험','네이버쇼핑 파트너','쇼핑윈도'].includes(t)) return;
                seen.add(t);
                out.push({text: t, href: (el.href||'').substring(0, 100), pos: [Math.round(r.x), Math.round(r.y)]});
            });
            return out;
        }
        """)

        return {"ok": True, "submenus": new_menus}
    except Exception as e:  # noqa: BLE001 - 상품등록 페이지 URL 탐색(읽기전용 리서치 스크립트) — 팝업무시/사이드바탐색실패/URL후보실패 모두 오류를 결과에 기록하고 계속 진행할 뿐 실제 등록 동작은 없음.
        return {"ok": False, "error": str(e)[:100]}


def _explore_hover(page):
    """1. 사이드바 hover 로 상품관리 펼침 시도."""
    # 1. 사이드바 hover로 상품관리 펼침 시도
    print("[1] 사이드바 '상품관리' hover로 펼침 시도")
    hover_r = try_sidebar_hover(page)
    if hover_r.get("ok"):
        subs = hover_r.get("submenus", [])
        print(f"  ✓ 펼친 후 하위 메뉴 {len(subs)}개")
        for s in subs[:20]:
            print(f"    - {s['text']:<25}  pos={s['pos']}")
    else:
        print(f"  ✗ {hover_r.get('reason', 'unknown')}")
    return hover_r


def _probe_candidates(page):
    """2. 추가 URL 후보 시도."""
    # 2. 추가 URL 후보 시도
    print(f"\n[2] 추가 URL 후보 시도 ({len(CANDIDATES_V2)}개)")
    results = []
    for i, suffix in enumerate(CANDIDATES_V2, 1):
        url = BASE + suffix
        print(f"  [{i:2}/{len(CANDIDATES_V2)}] {suffix:<40}", end=" ", flush=True)
        try:
            page.goto(url, timeout=12000, wait_until="domcontentloaded")
            time.sleep(3)
            info = analyze(page)
            info["candidate"] = suffix
            results.append(info)

            if info["is_group_product"]:
                print("  → 그룹상품 리다이렉트")
            elif info.get("is_error"):
                print("  ✗ 오류")
            elif info["price_input"] and info["stock_input"]:
                print(f"  ★★★ 가격+재고 input 발견! 필드 {info['field_count']}")
            elif info["price_input"] or info["stock_input"]:
                print(f"  △ 부분 (price={info['price_input']}, stock={info['stock_input']})")
            else:
                print(f"  · 필드{info['field_count']} URL={info['url'][-50:]}")
        except Exception as e:  # noqa: BLE001 - 상품등록 페이지 URL 탐색(읽기전용 리서치 스크립트) — 팝업무시/사이드바탐색실패/URL후보실패 모두 오류를 결과에 기록하고 계속 진행할 뿐 실제 등록 동작은 없음.
            print(f"  ✗ {str(e)[:30]}")
            results.append({"candidate": suffix, "error": str(e)[:100]})
    return results


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  일반 상품 등록 페이지 재탐색 v2")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    hover_r = _explore_hover(page)

    results = _probe_candidates(page)

    # 결과
    real_hits = [r for r in results if r.get("price_input") and r.get("stock_input")]
    print(f"\n  진짜 일반 상품 등록 페이지: {len(real_hits)}개")
    for r in real_hits:
        print(f"    ★ {r['candidate']}")
        print(f"       URL: {r['url']}")

    out = ROOT / "data" / "sitemap" / "smartstore_register_search_v2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"hover_result": hover_r, "url_results": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n  저장: {out.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 상품등록 페이지 URL 탐색(읽기전용 리서치 스크립트) — 팝업무시/사이드바탐색실패/URL후보실패 모두 오류를 결과에 기록하고 계속 진행할 뿐 실제 등록 동작은 없음.
        import traceback

        traceback.print_exc()
