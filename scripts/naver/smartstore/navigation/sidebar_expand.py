"""사이드바 자동 펼침 + 일반 상품 등록 메뉴 자동 발견.

흐름:
  1. 셀러센터 진입
  2. '좌측 내비게이션 펼쳐보기' 버튼 클릭 (사이드바 펼침)
  3. '상품관리' 메뉴 클릭 → 하위 펼침
  4. 하위 메뉴 전체 추출 + 각 메뉴 클릭으로 URL 발견
  5. 가격/재고 input 가진 페이지 자동 식별
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

BASE = "https://sell.smartstore.naver.com"
DASHBOARD = f"{BASE}/#/home/dashboard"
OUTPUT = ROOT / "data" / "sitemap" / "smartstore_sidebar_expanded.json"


def find_and_click_text(page, text: str, only_left: bool = True, wait_s: float = 2.5) -> dict:
    """텍스트 매칭 요소 좌표 + scrollIntoView + 실제 마우스 클릭.

    음수 좌표(화면 밖) 발견 시 scrollIntoView 후 좌표 재측정.
    """
    # 1단계: scrollIntoView로 요소를 화면 중앙으로
    scrolled = page.evaluate(
        r"""
    ({text, only_left}) => {
        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 || r.height > 0;  // 화면 밖이어도 size는 있음
        };
        for (const el of document.querySelectorAll('a, button, li, span, div[role="button"]')) {
            if (!isVisible(el)) continue;
            const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
            if (t === text) {
                const r = el.getBoundingClientRect();
                if (only_left && r.x > 280) continue;
                // 화면 중앙으로 스크롤
                el.scrollIntoView({block: 'center', behavior: 'instant'});
                return true;
            }
        }
        return false;
    }
    """,
        {"text": text, "only_left": only_left},
    )

    if not scrolled:
        return {"ok": False, "reason": "not_found"}

    time.sleep(0.5)  # 스크롤 안정화 대기

    # 2단계: 화면 안에 위치한 좌표 재측정
    candidates = page.evaluate(
        r"""
    ({text, only_left}) => {
        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const out = [];
        const vh = window.innerHeight;
        const vw = window.innerWidth;
        for (const el of document.querySelectorAll('a, button, li, span, div[role="button"]')) {
            if (!isVisible(el)) continue;
            const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
            if (t === text) {
                const r = el.getBoundingClientRect();
                if (only_left && r.x > 280) continue;
                // 화면 안에 있는지 확인
                const inView = r.y >= 0 && r.y < vh && r.x >= 0 && r.x < vw;
                out.push({
                    x: Math.round(r.x + r.width / 2),
                    y: Math.round(r.y + r.height / 2),
                    in_view: inView,
                });
            }
        }
        // 화면 안 우선
        out.sort((a, b) => (b.in_view ? 1 : 0) - (a.in_view ? 1 : 0));
        return out;
    }
    """,
        {"text": text, "only_left": only_left},
    )

    if not candidates:
        return {"ok": False, "reason": "not_found_after_scroll"}

    t = candidates[0]
    if t["y"] < 0 or t["x"] < 0:
        return {"ok": False, "reason": f"out_of_view:({t['x']},{t['y']})"}

    page.mouse.move(t["x"], t["y"])
    time.sleep(0.3)
    page.mouse.click(t["x"], t["y"])
    time.sleep(wait_s)
    return {"ok": True, "clicked_at": [t["x"], t["y"]], "in_view": t["in_view"]}


def extract_submenus_near(page, near_y: int, margin: int = 400) -> list[dict]:
    """특정 y 좌표 근처의 들여쓰기된 메뉴들 (펼쳐진 하위 메뉴)."""
    return page.evaluate(
        r"""
    ({nearY, margin}) => {
        const isVisible = (el) => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') return false;
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        };
        const out = [];
        const seen = new Set();
        document.querySelectorAll('a, li, button').forEach(el => {
            if (!isVisible(el)) return;
            const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
            if (!t || t.length < 2 || t.length > 30 || seen.has(t)) return;
            const r = el.getBoundingClientRect();
            // 들여쓰기 (x: 10~280) + 근처 y
            if (r.x >= 10 && r.x < 280 && Math.abs(r.y - nearY) < margin && r.height < 50) {
                seen.add(t);
                out.push({
                    text: t,
                    pos: [Math.round(r.x), Math.round(r.y)],
                    href: (el.href || '').substring(0, 200),
                });
            }
        });
        out.sort((a, b) => a.pos[1] - b.pos[1]);
        return out;
    }
    """,
        {"nearY": near_y, "margin": margin},
    )


def analyze_page(page) -> dict:
    return page.evaluate("""
    () => ({
        url: location.href,
        title: document.title,
        is_group: location.href.includes('standard-group-product'),
        field_count: document.querySelectorAll('input:not([type=hidden]), select, textarea').length,
        has_price_input: !!document.querySelector('input[name*="salePrice"], input[name*="sellPrice"]'),
        has_stock_input: !!document.querySelector('input[name*="stockQuantity"], input[name*="stock"]'),
    })
    """)


def _enter_and_expand(page) -> None:
    print("[1] 대시보드 진입")
    page.goto(DASHBOARD, timeout=20000, wait_until="domcontentloaded")
    time.sleep(5)
    try:
        handle_page_popups(page, timeout_s=2.0)
        close_popup_windows(page)
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        pass

    # 2. 사이드바 강제 펼침 (CSS 직접 조작)
    print("[2] 사이드바 강제 펼침 (CSS + 클릭)")
    expand_targets = [
        "좌측 내비게이션 펼쳐보기",
        "메뉴토글",
        "메뉴 토글",
    ]
    for t in expand_targets:
        r = find_and_click_text(page, t, only_left=False)
        if r.get("ok"):
            print(f"  ✓ '{t}' 클릭됨")
            break
    time.sleep(2)

    # CSS 강제: 사이드바 컨테이너의 transform/left 초기화
    print("  사이드바 CSS 강제 표시")
    page.evaluate("""
    (() => {
        // 사이드바 후보 모든 요소
        const sidebarSels = [
            '.gnb_lnb', '.lnb', '[class*="Sidebar"]', '[class*="LeftMenu"]',
            '[class*="GnbLnb"]', '[class*="SideMenu"]', 'aside',
            '[class*="navbar"]', '.lnb_wrap', '.left_menu', 'nav',
        ];
        for (const sel of sidebarSels) {
            document.querySelectorAll(sel).forEach(el => {
                const r = el.getBoundingClientRect();
                // 좌측에 있어야 할 메뉴가 화면 밖에 있는 경우
                if (r.x < 0 && r.height > 200) {
                    el.style.transform = 'translateX(0)';
                    el.style.left = '0';
                    el.style.marginLeft = '0';
                }
            });
        }
        // class에 'collapsed'/'closed' 있으면 제거
        document.querySelectorAll('.collapsed, .closed, .lnb-collapsed, [class*="collapse"]').forEach(el => {
            el.classList.remove('collapsed', 'closed', 'lnb-collapsed');
        });
        // body에 lnb 토글 class 있으면 제거
        document.body.classList.remove('lnb-collapsed', 'sidebar-collapsed', 'collapsed');
        document.documentElement.classList.remove('lnb-collapsed', 'sidebar-collapsed', 'collapsed');
    })();
    """)
    time.sleep(1.5)


def _locate_products_menu(page) -> dict | None:
    # 3. '상품관리' 클릭 (scrollIntoView 사용)
    print("\n[3] '상품관리' 클릭 (scrollIntoView)")
    r = find_and_click_text(page, "상품관리", only_left=True, wait_s=3.0)
    if not r.get("ok"):
        print(f"  ✗ {r.get('reason')}")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({"error": r.get("reason")}), encoding="utf-8")
        return None
    print(f"  ✓ 클릭 위치: {r.get('clicked_at')}")
    # 클릭 후 메뉴 위치 재측정 (스크롤된 상태)
    target_info = page.evaluate(r"""
    () => {
        for (const el of document.querySelectorAll('a, button, li, span')) {
            const s = window.getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden') continue;
            const t = (el.innerText || '').trim();
            if (t === '상품관리') {
                const r = el.getBoundingClientRect();
                if (r.x < 280 && r.y >= 0) {
                    return {y: Math.round(r.y + r.height/2), x: Math.round(r.x + r.width/2)};
                }
            }
        }
        return null;
    }
    """)
    if not target_info:
        print("  ✗ 상품관리 위치 재측정 실패")
        return None
    parent_y = target_info["y"]
    print(f"  현재 위치: ({target_info['x']}, {parent_y})")
    return target_info


def _collect_submenus(page, parent_y) -> list:
    # 4. 펼쳐진 하위 메뉴 추출
    print("\n[4] 하위 메뉴 추출")
    submenus = extract_submenus_near(page, parent_y, margin=600)
    # '상품관리' 자기 자신 제외 + 명백한 다른 메뉴 제외
    other_main_menus = [
        "검색하기",
        "상품관리",
        "판매관리",
        "정산관리",
        "문의/리뷰관리",
        "스토어관리",
        "혜택/마케팅",
        "N배송 관리",
        "커머스솔루션",
        "데이터분석",
        "광고관리",
        "프로모션 관리",
        "쇼핑 커넥트",
        "판매자 정보",
    ]
    submenus = [s for s in submenus if s["text"] not in other_main_menus]
    print(f"  발견: {len(submenus)}개")
    for s in submenus:
        print(f"    - {s['text']:<25}  pos={s['pos']}")
    return submenus


def _click_submenus(page, submenus, target_info, parent_y) -> list:
    # 5. 각 하위 메뉴 클릭 → URL 확인
    print("\n[5] 각 하위 메뉴 클릭 → URL/필드 확인")
    page_results = []
    for s in submenus[:15]:
        text = s["text"]
        print(f"  [클릭] {text:<25}", end=" ", flush=True)
        # 부모 다시 클릭 (펼침)
        page.mouse.move(target_info["x"], parent_y)
        time.sleep(0.3)
        page.mouse.click(target_info["x"], parent_y)
        time.sleep(2)
        # 하위 메뉴 클릭
        r = find_and_click_text(page, text, only_left=True, wait_s=3.0)
        if not r.get("ok"):
            print(f"  ✗ {r.get('reason')}")
            continue
        info = analyze_page(page)
        info["menu_text"] = text
        page_results.append(info)
        if info["is_group"]:
            print("  → 그룹상품")
        elif info["has_price_input"] and info["has_stock_input"]:
            print(f"  ★ 가격+재고 input! URL={info['url'][-60:]}")
        else:
            print(f"  · 필드{info['field_count']} URL={info['url'][-50:]}")
    return page_results


def _report_and_save(submenus, page_results) -> None:
    # 6. 진짜 일반 상품 등록 페이지
    real_hits = [r for r in page_results if r.get("has_price_input") and r.get("has_stock_input")]
    print(f"\n  진짜 상품 등록 페이지: {len(real_hits)}개")
    for r in real_hits:
        print(f"    ★ menu='{r['menu_text']}'  URL={r['url']}")

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "submenus": submenus,
                "page_results": page_results,
                "real_register_urls": [r["url"] for r in real_hits],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n  저장: {OUTPUT.name}")


def main():
    page = get_page()
    print(f"\n{'=' * 70}")
    print("  사이드바 자동 펼침 + 일반 상품 메뉴 발견")
    print(f"{'=' * 70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return
    _enter_and_expand(page)
    target_info = _locate_products_menu(page)
    if not target_info:
        return
    parent_y = target_info["y"]
    submenus = _collect_submenus(page, parent_y)
    page_results = _click_submenus(page, submenus, target_info, parent_y)
    _report_and_save(submenus, page_results)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - 팝업/닫기창 처리 브라우저자동화 실패 무시(best-effort), 최상위 main() 예외는 traceback 출력으로 진단정보 남김
        import traceback

        traceback.print_exc()
