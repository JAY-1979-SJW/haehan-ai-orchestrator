"""블로그 모듈의 실제 셀렉터 검증 + 보완용 데이터 수집.

실행:
  1. 블로그 어드민 페이지 진입 (admin.blog.naver.com)
  2. 이웃 목록 / 통계 / 댓글 페이지 DOM 분석
  3. 정확한 셀렉터 찾기
  4. 결과를 data/blog_selector_audit.json 으로 저장
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.popup_detector import handle_page_popups
from scripts.naver.auth import ensure_naver_login

BLOG_ID = "skyjwsin"
OUTPUT = ROOT / "data" / "blog_selector_audit.json"


def analyze_blog_main(page) -> dict:
    """블로그 메인 — 통계/이웃 카운트 정확 추출."""
    page.goto(f"https://blog.naver.com/{BLOG_ID}", timeout=15000, wait_until="domcontentloaded")
    time.sleep(3)
    try:
        handle_page_popups(page, timeout_s=1.5)
    except Exception:
        pass

    return page.evaluate("""
    () => {
        const txt = (document.body?.innerText || '');
        // 통계 영역 후보
        const stats = {};
        // 방문/이웃 카운트 패턴 (다양한 표현)
        const patterns = {
            visitor_today: [/오늘\\s*[:\\s]*([\\d,]+)/, /today\\s*[:\\s]*([\\d,]+)/i],
            visitor_total: [/전체\\s*[:\\s]*([\\d,]+)/, /total\\s*[:\\s]*([\\d,]+)/i],
            post_count: [/포스트\\s*[:\\s]*([\\d,]+)/, /글\\s*[:\\s]*([\\d,]+)/],
            neighbor_count: [/이웃\\s*[:\\s]*([\\d,]+)/],
        };
        for (const [k, patList] of Object.entries(patterns)) {
            for (const pat of patList) {
                const m = pat.exec(txt);
                if (m) {
                    stats[k] = parseInt(m[1].replace(/,/g, ''));
                    break;
                }
            }
        }
        // 통계 요소 DOM 셀렉터 후보
        const stat_selectors = [];
        document.querySelectorAll('[class*="visit"], [class*="counter"], [class*="stats"], .num').forEach(el => {
            if (el.offsetParent === null) return;
            const t = (el.innerText || '').trim();
            if (t && /\\d+/.test(t) && t.length < 30) {
                stat_selectors.push({cls: el.className.substring(0, 60), text: t.substring(0, 30)});
            }
        });
        return {url: location.href, title: document.title, stats, stat_selectors: stat_selectors.slice(0, 20)};
    }
    """)


def analyze_admin_main(page) -> dict:
    """블로그 어드민 메인."""
    page.goto(f"https://admin.blog.naver.com/{BLOG_ID}",
              timeout=15000, wait_until="domcontentloaded")
    time.sleep(3)
    try:
        handle_page_popups(page, timeout_s=1.5)
    except Exception:
        pass

    return page.evaluate("""
    () => {
        const result = {url: location.href, title: document.title};
        // 사이드 메뉴
        const menus = [];
        document.querySelectorAll('a, button').forEach(el => {
            if (el.offsetParent === null) return;
            const t = (el.innerText || '').trim();
            const href = el.href || '';
            if (t && t.length > 1 && t.length < 30 &&
                (href.includes('admin.blog.naver') || /이웃|글|통계|관리|시리즈/.test(t))) {
                menus.push({text: t, href: href.substring(0, 150)});
            }
        });
        const seen = new Set();
        result.menus = menus.filter(m => {
            if (seen.has(m.text)) return false;
            seen.add(m.text);
            return true;
        }).slice(0, 40);
        return result;
    }
    """)


def analyze_neighbor_list(page) -> dict:
    """이웃 관리 페이지."""
    page.goto(f"https://admin.blog.naver.com/{BLOG_ID}/buddy/list",
              timeout=15000, wait_until="domcontentloaded")
    time.sleep(3)
    try:
        handle_page_popups(page, timeout_s=1.5)
    except Exception:
        pass

    return page.evaluate("""
    () => {
        const result = {url: location.href};
        // 이웃 항목 후보
        const items = [];
        const seen = new Set();
        // 다양한 셀렉터 시도
        const sels = ['.buddy_list li', '[class*="neighbor"] li', 'table tbody tr',
                     '[class*="Buddy"] li', '.list_item', 'ul li'];
        for (const sel of sels) {
            const els = document.querySelectorAll(sel);
            if (els.length > 3) {
                els.forEach((el, i) => {
                    if (i >= 5) return;
                    const html_short = el.outerHTML.substring(0, 300);
                    const text = (el.innerText || '').substring(0, 100);
                    items.push({selector: sel, text: text, html: html_short});
                });
                if (items.length > 0) break;
            }
        }
        result.candidates = items;
        return result;
    }
    """)


def main():
    page = get_page()
    print(f"\n{'='*70}")
    print(f"  블로그 모듈 셀렉터 실제 검증")
    print(f"{'='*70}\n")

    r = ensure_naver_login(page)
    if not r.get("ok"):
        print("✗ 로그인 실패")
        return

    print("[1] 블로그 메인 — 통계 셀렉터")
    main_r = analyze_blog_main(page)
    print(f"  URL: {main_r['url']}")
    print(f"  자동 추출 통계: {main_r['stats']}")
    print(f"  통계 후보 DOM 요소 ({len(main_r['stat_selectors'])}개):")
    for s in main_r['stat_selectors'][:10]:
        print(f"    cls={s['cls']:<40} text='{s['text']}'")

    print("\n[2] 블로그 어드민 메인 메뉴")
    admin_r = analyze_admin_main(page)
    print(f"  URL: {admin_r['url']}")
    print(f"  메뉴 ({len(admin_r.get('menus', []))}개):")
    for m in admin_r.get('menus', [])[:15]:
        print(f"    - {m['text']:<25} {m['href'][:80]}")

    print("\n[3] 이웃 관리 페이지")
    nb_r = analyze_neighbor_list(page)
    print(f"  URL: {nb_r['url']}")
    cands = nb_r.get('candidates', [])
    print(f"  후보 셀렉터 ({len(cands)}개):")
    for c in cands[:3]:
        print(f"    sel={c['selector']}")
        print(f"      text: {c['text'][:80]}")

    # 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "blog_main": main_r, "admin_main": admin_r, "neighbor_list": nb_r,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 저장: {OUTPUT.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
