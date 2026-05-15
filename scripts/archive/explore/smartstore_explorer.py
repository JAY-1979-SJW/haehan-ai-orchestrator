"""네이버 스마트스토어 셀러센터 깊은 사이트맵 탐색.

스마트스토어는 SPA(해시 라우팅)이라 일반 page.goto로는 컨텐츠 추출 불가.
이 모듈은:
  1. 좌측 사이드바 메뉴 전체 트리 추출
  2. 각 메뉴 JS 클릭 시뮬레이션 → 컨텐츠 로드 대기 → 메타 추출
  3. 상품 등록 페이지는 폼 필드 상세 분석
  4. 결과를 data/sitemap/sell.smartstore.naver.com_deep.json 으로 저장

사용:
  python scripts/smartstore_explorer.py             # 전체 메뉴 탐색
  python scripts/smartstore_explorer.py --product-only  # 상품 관련만
  python scripts/smartstore_explorer.py --max-pages 50

전제: 이미 로그인된 상태 (login_post_capture 또는 사용자가 직접 로그인)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.popup_detector import handle_page_popups
from scripts.login_detector import is_logged_in_generic, get_logged_in_user
from scripts.critical_logger import log_critical
from scripts.logger import get_logger

_log = get_logger(__name__)
SITEMAP_DIR = ROOT / "data" / "sitemap"
SELLER_BASE = "https://sell.smartstore.naver.com"


# ── 사이드바 메뉴 트리 추출 ────────────────────────────────────────────────

EXTRACT_SIDEBAR_JS = r"""
() => {
    // 스마트스토어 셀러센터: 좌측 사이드바가 <li> 태그로 좌측 영역 (x<60)에 배치됨
    // 클릭하면 펼쳐지는 구조. 우선 보이는 메뉴 항목들 모두 추출.

    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const result = {
        url: location.href,
        title: document.title,
        captured_at: new Date().toISOString(),
        sidebar_menus: [],
        top_menus: [],
    };

    // 1. 좌측 영역의 LI/A 모두 추출 (x < 280, y > 100 — 헤더 제외)
    const seen = new Set();
    document.querySelectorAll('a, li, button').forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (!text || text.length < 2 || text.length > 25) return;
        if (seen.has(text)) return;
        const r = el.getBoundingClientRect();
        // 좌측 영역 + 헤더 아래
        if (r.x >= -10 && r.x < 280 && r.y > 100 && r.height < 50) {
            seen.add(text);
            // depth 추정 (x 좌표 기반)
            let depth = 1;
            if (r.x > 30) depth = 2;
            if (r.x > 60) depth = 3;
            result.sidebar_menus.push({
                depth: depth,
                text: text,
                href: (el.href || '').substring(0, 200),
                tag: el.tagName,
                pos: [Math.round(r.x), Math.round(r.y)],
                cls: (el.className || '').substring(0, 60),
            });
        }
    });

    // y좌표 순 정렬
    result.sidebar_menus.sort((a, b) => a.pos[1] - b.pos[1]);

    // 2. 상단 GNB 메뉴
    document.querySelectorAll('header a, [class*="Header"] a, [class*="Gnb"] a, [class*="gnb"] a').forEach(a => {
        if (!isVisible(a)) return;
        const text = (a.innerText || '').trim().replace(/\s+/g, ' ').substring(0, 40);
        const r = a.getBoundingClientRect();
        if (text && text.length >= 2 && r.y < 100) {
            result.top_menus.push({text: text, href: (a.href || '').substring(0, 200)});
        }
    });

    return result;
}
"""


# ── 페이지 컨텐츠 분석 ──────────────────────────────────────────────────────

ANALYZE_PAGE_JS = r"""
() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const result = {
        url: location.href,
        title: document.title,
        captured_at: new Date().toISOString(),
    };

    // 1. 페이지 제목 영역
    const h1 = document.querySelector('h1, h2, [class*="title"], [class*="Title"]');
    result.heading = h1 ? (h1.innerText || '').trim().substring(0, 100) : '';

    // 2. 폼 입력 필드 (상품 등록 등 분석용)
    const fields = [];
    document.querySelectorAll('input, select, textarea').forEach(el => {
        if (!isVisible(el)) return;
        const type = (el.type || el.tagName).toLowerCase();
        if (type === 'hidden') return;
        const label = el.getAttribute('aria-label') || el.placeholder || '';
        // 라벨 찾기 (input 주변 label 또는 부모의 텍스트)
        let labelText = label;
        if (!labelText && el.id) {
            const l = document.querySelector(`label[for="${el.id}"]`);
            if (l) labelText = (l.innerText || '').trim();
        }
        if (!labelText) {
            // 부모 형제에서 텍스트 찾기
            const parent = el.parentElement;
            if (parent) {
                const sibling = parent.previousElementSibling || parent.querySelector('label, .label, [class*="label"]');
                if (sibling) labelText = (sibling.innerText || '').trim().substring(0, 30);
            }
        }
        fields.push({
            type: type,
            name: el.name || el.id || '',
            label: labelText.substring(0, 50),
            required: el.required || el.getAttribute('aria-required') === 'true',
            placeholder: el.placeholder || '',
        });
    });
    result.fields = fields.slice(0, 100);
    result.field_count = fields.length;

    // 3. 버튼들 (액션)
    const buttons = [];
    document.querySelectorAll('button, a.btn, a[role=button], input[type=submit], input[type=button]').forEach(b => {
        if (!isVisible(b)) return;
        const text = (b.innerText || b.value || '').trim().substring(0, 30);
        if (text && text.length >= 2) {
            buttons.push({
                text: text,
                tag: b.tagName,
                cls: (b.className || '').substring(0, 60),
                onclick: (b.getAttribute('onclick') || '').substring(0, 80),
            });
        }
    });
    result.buttons = buttons.slice(0, 30);

    // 4. 테이블 (목록 페이지 식별용)
    const tables = [];
    document.querySelectorAll('table').forEach(t => {
        if (!isVisible(t)) return;
        const headers = Array.from(t.querySelectorAll('thead th, thead td')).map(h =>
            (h.innerText || '').trim().substring(0, 30)
        ).filter(Boolean);
        const rowCount = t.querySelectorAll('tbody tr').length;
        tables.push({ headers: headers, row_count: rowCount });
    });
    result.tables = tables.slice(0, 5);

    // 5. 카테고리/탭
    const tabs = [];
    document.querySelectorAll('[role=tab], .tab, .tabs > *, [class*="Tab"]:not([class*="tabContent"])').forEach(t => {
        if (!isVisible(t)) return;
        const text = (t.innerText || '').trim().substring(0, 30);
        if (text && text.length >= 1 && text.length <= 30) {
            tabs.push({ text: text });
        }
    });
    result.tabs = tabs.slice(0, 20);

    // 6. 페이지 분류 (heuristic)
    const txt = (document.body?.innerText || '').toLowerCase();
    result.is_product_register = /상품\s*등록|판매상품\s*등록|new\s*product/i.test(txt) ||
                                 /상품등록/.test(result.heading);
    result.is_order_mgmt = /주문\s*관리|배송\s*관리|order|delivery/i.test(txt);
    result.is_settlement = /정산|매출|수익|settlement/i.test(txt);
    result.is_statistics = /통계|분석|statistics/i.test(txt);

    return result;
}
"""


# ── 메뉴 클릭 + 페이지 변화 대기 ─────────────────────────────────────────────

def click_menu_and_wait(page, menu_item: dict, wait_s: float = 2.5) -> bool:
    """메뉴 클릭 후 URL 해시 또는 컨텐츠 변화 대기. li/a/button 모두 시도."""
    href = menu_item.get("href", "")
    text = menu_item.get("text", "")
    before_url = page.url

    try:
        # 텍스트로 클릭 (a/li/button 모두) - 정확한 텍스트 매칭
        clicked = page.evaluate("""
        (text) => {
            const isVisible = (el) => {
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            // 좌측 영역에서 정확 매칭 우선
            const all = document.querySelectorAll('a, button, li, [role=menuitem], [role=button]');
            for (const el of all) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
                if (t === text) {
                    const r = el.getBoundingClientRect();
                    if (r.x < 280) {  // 좌측 영역 우선
                        el.click();
                        return {ok: true, tag: el.tagName, x: Math.round(r.x)};
                    }
                }
            }
            // fallback: 전 영역에서 정확 매칭
            for (const el of all) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
                if (t === text) {
                    el.click();
                    return {ok: true, tag: el.tagName, x: -1};
                }
            }
            return {ok: false};
        }
        """, text)

        if not clicked or not clicked.get("ok"):
            return False

        # URL 변화 또는 시간 경과 대기
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if page.url != before_url:
                break
            time.sleep(0.3)
        time.sleep(1.2)  # 컨텐츠 + 하위메뉴 펼침 대기
        return True

    except Exception as e:
        _log.debug("메뉴 클릭 실패 (%s): %s", text, e)
        return False


# ── 클릭 후 펼쳐진 하위 메뉴 추출 ─────────────────────────────────────────────

EXTRACT_SUBMENU_JS = r"""
(parentY) => {
    // 부모 메뉴 클릭 후 펼쳐진 하위 메뉴 추출
    // 보통 부모 아래에 새로 나타난 메뉴들 (들여쓴 형태)
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
    };

    const sub = [];
    const seen = new Set();
    document.querySelectorAll('a, li, button').forEach(el => {
        if (!isVisible(el)) return;
        const text = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
        if (!text || text.length < 2 || text.length > 25 || seen.has(text)) return;
        const r = el.getBoundingClientRect();
        // 좌측 영역 + 부모 메뉴 근처 (위/아래 200px 이내) + 들여쓰기 (x>10)
        if (r.x >= 5 && r.x < 280 && Math.abs(r.y - parentY) < 250 && r.x > 10) {
            seen.add(text);
            sub.push({
                text: text,
                tag: el.tagName,
                href: (el.href || '').substring(0, 200),
                pos: [Math.round(r.x), Math.round(r.y)],
            });
        }
    });
    return sub;
}
"""


# ── 메인 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--product-only", action="store_true", help="상품 관련 메뉴만")
    parser.add_argument("--wait", type=float, default=2.5)
    args = parser.parse_args()

    page = get_page()

    print(f"\n{'='*70}")
    print(f"  스마트스토어 셀러센터 깊은 사이트맵 탐색")
    print(f"{'='*70}\n")

    # 1. 로그인 상태 확인
    print("  [1] 로그인 상태 확인...")
    if not page.url.startswith(SELLER_BASE):
        page.goto(f"{SELLER_BASE}/#/home/dashboard", timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)
    try:
        handle_page_popups(page, timeout_s=2.0)
    except Exception:
        pass

    if not is_logged_in_generic(page):
        print("  ✗ 로그인되지 않은 상태입니다.")
        print("  먼저 login_post_capture.py 또는 직접 로그인하세요.")
        sys.exit(1)

    user = get_logged_in_user(page) or "(미감지)"
    print(f"  ✓ 로그인 상태: {user}")
    log_critical("OTHER", f"스마트스토어 깊은 탐색 시작", user=user, mode="deep_explorer_start")

    # 2. 사이드바 메뉴 트리 추출
    print(f"\n  [2] 사이드바 메뉴 트리 추출...")
    time.sleep(2)
    sidebar = page.evaluate(EXTRACT_SIDEBAR_JS)
    menus = sidebar.get("sidebar_menus", [])
    top_menus = sidebar.get("top_menus", [])
    print(f"  ✓ 사이드바 메뉴: {len(menus)}개  (depth별: " +
          ", ".join(f"L{d}={sum(1 for m in menus if m['depth']==d)}" for d in sorted({m['depth'] for m in menus})) + ")")
    print(f"  ✓ 상단 메뉴: {len(top_menus)}개")

    # 제품 관련만 필터
    if args.product_only:
        before = len(menus)
        product_kws = ["상품", "판매", "재고", "옵션", "카테고리", "product", "상세"]
        menus = [m for m in menus if any(k in m["text"] for k in product_kws)]
        print(f"  ✓ product-only 필터: {before} → {len(menus)}개")

    if args.max_pages > 0:
        menus = menus[: args.max_pages]

    # 3. 각 메뉴 클릭 → 하위 메뉴 펼침 → 하위 메뉴 페이지 진입
    print(f"\n  [3] 메뉴 클릭 + 하위 메뉴 펼침 + 페이지 메타 수집...")
    pages_data = []
    all_submenus = []  # 메뉴별 하위 메뉴 트리

    for i, m in enumerate(menus, 1):
        text = m["text"]
        depth = m["depth"]
        parent_y = m.get("pos", [0, 0])[1]
        print(f"    [{i:2}/{len(menus)}] {text[:25]:<27}", end=" ", flush=True)

        # 1. 메뉴 클릭 (펼침)
        clicked = click_menu_and_wait(page, m, wait_s=args.wait)
        if not clicked:
            print("✗ 클릭실패")
            pages_data.append({**m, "error": "click_failed"})
            continue

        # 2. 하위 메뉴 추출
        try:
            submenu = page.evaluate(EXTRACT_SUBMENU_JS, parent_y)
            # 상위 메뉴 자체 텍스트 제외
            submenu = [s for s in submenu if s["text"] != text]
            print(f"✓ 하위 {len(submenu)}개", end=" ")
        except Exception as e:
            submenu = []
            print(f"하위추출실패 {str(e)[:30]}", end=" ")

        all_submenus.append({"parent": text, "items": submenu})

        # 3. 현재 페이지 (메뉴 클릭으로 이동된 경우) 메타 추출
        try:
            try:
                handle_page_popups(page, timeout_s=1.0)
            except Exception:
                pass
            page_meta = page.evaluate(ANALYZE_PAGE_JS)
            page_meta["menu_text"] = text
            page_meta["menu_depth"] = depth
            page_meta["submenu_count"] = len(submenu)
            pages_data.append(page_meta)

            tags = []
            if page_meta.get("is_product_register"): tags.append("상품등록")
            if page_meta.get("is_order_mgmt"): tags.append("주문")
            if page_meta.get("is_settlement"): tags.append("정산")
            if page_meta.get("is_statistics"): tags.append("통계")
            tag_str = " " + ",".join(tags) if tags else ""

            print(f"필드:{page_meta.get('field_count', 0)} 버튼:{len(page_meta.get('buttons',[]))}{tag_str}")
        except Exception as e:
            print(f"메타실패 {str(e)[:30]}")
            pages_data.append({**m, "error": str(e)[:80]})

    # 3-2. 하위 메뉴 페이지 진입 (각 하위 메뉴 클릭 → 페이지 메타 수집)
    print(f"\n  [3-2] 하위 메뉴 페이지 수집...")
    submenu_pages = []
    total_subs = sum(len(s["items"]) for s in all_submenus)
    print(f"    총 하위 메뉴 {total_subs}개")
    cnt = 0
    for sub_group in all_submenus:
        parent_text = sub_group["parent"]
        for sub in sub_group["items"][:8]:  # 그룹당 최대 8개
            cnt += 1
            sub_text = sub["text"]
            print(f"    [{cnt:>3}/{total_subs}] {parent_text[:12]:<14} > {sub_text[:20]:<22}", end=" ", flush=True)

            # 부모 메뉴 먼저 다시 클릭 (펼침)
            click_menu_and_wait(page, {"text": parent_text}, wait_s=1.5)
            # 하위 메뉴 클릭
            ok = click_menu_and_wait(page, sub, wait_s=args.wait)
            if not ok:
                print("✗")
                continue
            try:
                page_meta = page.evaluate(ANALYZE_PAGE_JS)
                page_meta["parent_menu"] = parent_text
                page_meta["menu_text"] = sub_text
                submenu_pages.append(page_meta)
                tags = []
                if page_meta.get("is_product_register"): tags.append("상품등록")
                if page_meta.get("is_order_mgmt"): tags.append("주문")
                if page_meta.get("is_settlement"): tags.append("정산")
                tag_str = " " + ",".join(tags) if tags else ""
                print(f"✓ 필드:{page_meta.get('field_count', 0)} 버튼:{len(page_meta.get('buttons',[]))}{tag_str}  → {page_meta.get('url','')[-60:]}")
            except Exception as e:
                print(f"✗ {str(e)[:30]}")

    # 4. 상품 등록 페이지 식별 (메인 + 하위 모두)
    print(f"\n  [4] 상품 등록 페이지 식별...")
    all_pages = pages_data + submenu_pages
    product_register_pages = [p for p in all_pages if p.get("is_product_register")]
    if product_register_pages:
        print(f"  ✓ 상품 등록 페이지 {len(product_register_pages)}개 발견:")
        for p in product_register_pages:
            print(f"    - {p.get('menu_text', '')}: {p.get('heading', '')[:50]}")
            print(f"      입력 필드 {p.get('field_count', 0)}개, 버튼 {len(p.get('buttons', []))}개")
    else:
        print(f"  ⚠ 상품 등록 페이지를 직접 발견 못함 — '판매상품관리' 또는 메뉴에서 수동 진입 필요")

    # 5. 저장
    print(f"\n  [5] 사이트맵 저장...")
    out_data = {
        "domain": "sell.smartstore.naver.com",
        "category": "PORTAL_VISIT",
        "deep_explored_at": datetime.now().isoformat(timespec="seconds"),
        "user": user,
        "main_dashboard": {
            "url": sidebar.get("url"),
            "title": sidebar.get("title"),
        },
        "top_menus": top_menus,
        "sidebar_menu_tree": menus,
        "submenu_tree": all_submenus,
        "menu_count": len(menus),
        "submenu_count": sum(len(s["items"]) for s in all_submenus),
        "pages": pages_data,
        "submenu_pages": submenu_pages,
        "product_register_pages": product_register_pages,
        "summary": {
            "main_pages": len(pages_data),
            "submenu_pages": len(submenu_pages),
            "total_success": sum(1 for p in all_pages if not p.get("error")),
            "product_register_count": len(product_register_pages),
            "order_mgmt_count": sum(1 for p in all_pages if p.get("is_order_mgmt")),
            "settlement_count": sum(1 for p in all_pages if p.get("is_settlement")),
        },
    }

    out_path = SITEMAP_DIR / "sell.smartstore.naver.com_deep.json"
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 저장: {out_path}")

    log_critical("OTHER", "스마트스토어 깊은 탐색 완료",
                 user=user, menu_count=len(menus), pages=len(pages_data),
                 product_register=len(product_register_pages), mode="deep_explorer_done")

    print(f"\n{'='*70}")
    print(f"  완료  |  메뉴 {len(menus)} | 페이지 {out_data['summary']['success_count']}/{len(pages_data)} 추출")
    print(f"  상품등록 {len(product_register_pages)} | 주문 {out_data['summary']['order_mgmt_count']} | 정산 {out_data['summary']['settlement_count']}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
    except Exception as e:
        _log.error("실패: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)
