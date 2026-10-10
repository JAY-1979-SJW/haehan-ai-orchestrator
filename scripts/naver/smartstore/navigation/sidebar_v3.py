"""사이드바 자동 펼침 v3 — 새로운 접근.

핵심 개선:
  1. 페이지 새로고침으로 깨끗한 상태 시작
  2. 사이드바 상태를 명확히 검증 (펼침 vs 접힘)
  3. 메뉴 발견 → 즉시 클릭 (재측정 없이)
  4. 클릭 후 URL 변화 확인
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.browser.popup.popup_detector import close_popup_windows, handle_page_popups  # noqa: E402
from scripts.naver.common.auth import ensure_naver_login  # noqa: E402

BASE = "https://sell.smartstore.naver.com"
DASHBOARD = f"{BASE}/#/home/dashboard"


def check_sidebar_state(page) -> dict:
    """사이드바 펼침 상태 검증."""
    return page.evaluate(r"""
    () => {
        // 사이드바 후보 컨테이너 찾기
        const candidates = document.querySelectorAll(
            'aside, nav, [class*="lnb"], [class*="LNB"], [class*="sidebar"], [class*="Sidebar"], [class*="leftMenu"], [class*="LeftMenu"]'
        );
        const result = {expanded: false, width: 0, sidebar_count: candidates.length};
        let maxW = 0;
        let bestSidebar = null;
        for (const c of candidates) {
            const s = window.getComputedStyle(c);
            if (s.display === 'none') continue;
            const r = c.getBoundingClientRect();
            // 좌측에 있고 큰 높이
            if (r.x < 50 && r.height > 300 && r.width > maxW) {
                maxW = r.width;
                bestSidebar = c;
            }
        }
        if (bestSidebar) {
            const r = bestSidebar.getBoundingClientRect();
            result.expanded = r.width > 150;
            result.width = Math.round(r.width);
            result.height = Math.round(r.height);
            result.tag = bestSidebar.tagName;
            result.cls = bestSidebar.className.substring(0, 60);
            // 사이드바 내 메뉴 카운트
            result.menu_count = bestSidebar.querySelectorAll('a, li, button').length;
        }
        // 현재 좌측 영역에서 보이는 '상품관리' 텍스트의 좌표
        for (const el of document.querySelectorAll('a, li, button, span')) {
            const s = window.getComputedStyle(el);
            if (s.display === 'none') continue;
            const t = (el.innerText || '').trim();
            if (t === '상품관리') {
                const r = el.getBoundingClientRect();
                result.product_mgmt = {
                    x: Math.round(r.x), y: Math.round(r.y),
                    cx: Math.round(r.x + r.width/2),
                    cy: Math.round(r.y + r.height/2),
                    in_view: r.x >= 0 && r.y >= 0 && r.x < 1700 && r.y < 1000,
                };
                break;
            }
        }
        return result;
    }
    """)


def _refresh_dashboard(page) -> None:
    # 페이지 새로고침으로 깨끗한 상태
    print("[1] 페이지 새로고침")
    page.goto(DASHBOARD, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        pass


def _find_product_pos(page):
    # 사이드바 상태 검증
    print("[2] 사이드바 초기 상태")
    s1 = check_sidebar_state(page)
    print(f"  사이드바 후보: {s1.get('sidebar_count')}개")
    print(f"  최대 사이드바 width: {s1.get('width')}px expanded={s1.get('expanded')}")
    print(f"  '상품관리' 좌표: {s1.get('product_mgmt')}")

    # ★ 토글 클릭은 사이드바를 오히려 접는다. 초기 상태가 이미 펼쳐진 상태이므로 클릭 X
    if s1.get("product_mgmt", {}).get("in_view"):
        print("\n[3] 사이드바 이미 펼쳐진 상태 — 토글 클릭 생략")
        product_pos = s1.get("product_mgmt")
    else:
        print("\n[3] 화면 위로 스크롤")
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
        s2 = check_sidebar_state(page)
        product_pos = s2.get("product_mgmt")
    return product_pos


def _click_and_collect_menus(page, product_pos):
    # 즉시 클릭
    print(f"\n[5] '상품관리' 즉시 클릭 @ ({product_pos['cx']}, {product_pos['cy']})")
    page.mouse.move(product_pos["cx"], product_pos["cy"])
    time.sleep(0.5)
    page.mouse.click(product_pos["cx"], product_pos["cy"])
    time.sleep(3)

    # 펼친 후 즉시 모든 클릭 가능 요소 좌표 수집
    print("\n[6] 펼침 후 즉시 좌측 영역 메뉴 좌표 수집")
    menus = page.evaluate(r"""
    () => {
        const out = [];
        const seen = new Set();
        document.querySelectorAll('a, li, button').forEach(el => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.x > 300 || r.y < 100 || r.y > 900) return;
            const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
            if (!t || t.length < 2 || t.length > 25 || seen.has(t)) return;
            seen.add(t);
            out.push({
                text: t,
                pos: [Math.round(r.x), Math.round(r.y)],
                cx: Math.round(r.x + r.width/2),
                cy: Math.round(r.y + r.height/2),
            });
        });
        out.sort((a, b) => a.pos[1] - b.pos[1]);
        return out;
    }
    """)
    print(f"  좌측 메뉴 {len(menus)}개:")
    for m in menus[:30]:
        print(f"    {m['text']:<22} pos={m['pos']}")
    return menus


def _try_register_menus(page, menus, product_pos) -> None:
    # 상품 등록 관련 메뉴 즉시 클릭
    print("\n[7] '상품 등록' 직접 클릭")
    target_texts = ["상품 등록", "상품 조회/수정", "상품 관리", "상품 일괄등록"]
    found_url = None
    for t in target_texts:
        match = next((m for m in menus if m["text"] == t), None)
        if not match:
            print(f"  ✗ '{t}' 메뉴 없음")
            continue
        print(f"  '{t}' @ ({match['cx']}, {match['cy']}) 클릭", end=" ", flush=True)
        page.mouse.move(match["cx"], match["cy"])
        time.sleep(0.4)
        page.mouse.click(match["cx"], match["cy"])
        time.sleep(3)
        after = page.url
        print(f"→ URL: {after[-70:]}")
        # 가격/재고 input 검사
        check = page.evaluate("""
        () => ({
            has_price: !!document.querySelector('input[name*="salePrice"], input[name*="sellPrice"]'),
            has_stock: !!document.querySelector('input[name*="stockQuantity"], input[name*="stock"]'),
            is_group: location.href.includes('standard-group-product'),
        })
        """)
        if check["has_price"] and check["has_stock"]:
            print("      ★ 가격+재고 input 발견!")
            found_url = after
            break
        elif not check["is_group"]:
            print(f"      △ 그룹상품 아님, price={check['has_price']} stock={check['has_stock']}")
            found_url = after
        # 상품관리 다시 클릭으로 메뉴 펼침
        page.mouse.move(product_pos["cx"], product_pos["cy"])
        time.sleep(0.3)
        page.mouse.click(product_pos["cx"], product_pos["cy"])
        time.sleep(2)

    if found_url:
        print(f"\n  ★ 발견: {found_url}")
    else:
        print("\n  ✗ 일반 상품 등록 페이지 못 찾음 — 모두 그룹상품 리다이렉트")


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  사이드바 v3 — 새로고침 + 검증 + 즉시 클릭")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    _refresh_dashboard(page)
    product_pos = _find_product_pos(page)

    if not (product_pos and product_pos.get("in_view")):
        print("\n  ✗ '상품관리'가 화면 안에 없음")
        return

    menus = _click_and_collect_menus(page, product_pos)
    _try_register_menus(page, menus, product_pos)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        import traceback

        traceback.print_exc()
