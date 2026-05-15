"""블로그 모듈 정밀 셀렉터 발견 — 통계/이웃/댓글.

1. 어드민에서 "내 블로그 통계" 메뉴 → 진짜 URL 확보
2. 통계 페이지의 정확한 카운터 셀렉터 (달력 false-positive 제거)
3. "이웃블로그" 메뉴 → 진짜 이웃 페이지 URL
4. 포스트에서 댓글 답글 폼 UI 분석
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
OUTPUT = ROOT / "data" / "blog_deep_audit.json"


def main():
    page = get_page()
    print(f"\n{'='*70}")
    print(f"  블로그 정밀 셀렉터 발견")
    print(f"{'='*70}\n")

    ensure_naver_login(page)
    result = {}

    # 1. 어드민 메인 진입
    print("[1] 어드민 메인 진입")
    page.goto(f"https://admin.blog.naver.com/{BLOG_ID}", timeout=15000,
              wait_until="domcontentloaded")
    time.sleep(3)
    try:
        handle_page_popups(page, timeout_s=1.5)
    except Exception:
        pass

    # 2. 좌측 메뉴 좌표 + href 추출
    print("[2] 좌측 메뉴 좌표 추출")
    menus = page.evaluate(r"""
    () => {
        const out = [];
        document.querySelectorAll('a, button').forEach(el => {
            const s = window.getComputedStyle(el);
            if (s.display === 'none') return;
            const t = (el.innerText || '').trim();
            if (!t || t.length < 2 || t.length > 30) return;
            const r = el.getBoundingClientRect();
            if (r.x > 300 || r.y < 60 || r.y > 1000) return;
            out.push({text: t, href: (el.href || '').substring(0, 200),
                      pos: [Math.round(r.x), Math.round(r.y)]});
        });
        return out;
    }
    """)
    result["left_menus"] = menus
    print(f"  좌측 메뉴 {len(menus)}개")

    # 3. "내 블로그 통계" 클릭 (좌표 기반)
    stat_menu = next((m for m in menus if "통계" in m["text"]), None)
    if stat_menu:
        print(f"\n[3] '{stat_menu['text']}' 클릭")
        if stat_menu["href"] and stat_menu["href"].startswith("http"):
            page.goto(stat_menu["href"], timeout=15000, wait_until="domcontentloaded")
        else:
            page.mouse.move(stat_menu["pos"][0] + 30, stat_menu["pos"][1] + 10)
            time.sleep(0.4)
            page.mouse.click(stat_menu["pos"][0] + 30, stat_menu["pos"][1] + 10)
        time.sleep(4)
        print(f"  URL: {page.url}")

        # 통계 페이지 정밀 분석
        stat_data = {}
        for f in [page.main_frame] + [fr for fr in page.frames if fr != page.main_frame]:
            try:
                d = f.evaluate(r"""
                () => {
                    // 큰 숫자(통계) 후보 + 주변 라벨
                    const candidates = [];
                    document.querySelectorAll('*').forEach(el => {
                        const t = (el.innerText || '').trim();
                        if (!/^[\d,]+$/.test(t)) return;
                        const num = parseInt(t.replace(/,/g, ''));
                        // 달력 날짜 제외 (1~31의 단순 숫자)
                        if (num >= 1 && num <= 31 && t.length <= 2) return;
                        // 0 단독 제외
                        if (num === 0 && t === '0') {}
                        // 부모/형제 라벨
                        let label = '';
                        const parent = el.parentElement;
                        if (parent) {
                            // 형제 텍스트
                            const sib = parent.querySelector(':scope > *:not(:has(' + el.tagName + '))');
                            // 부모 자체 텍스트에서 숫자 빼기
                            const ptext = (parent.innerText || '').replace(t, '').trim().substring(0, 50);
                            if (ptext) label = ptext;
                        }
                        candidates.push({
                            num, text: t, label,
                            cls: (el.className || '').toString().substring(0, 50),
                            tag: el.tagName,
                        });
                    });
                    return {
                        url: location.href,
                        body_sample: (document.body?.innerText || '').substring(0, 800),
                        candidates: candidates.slice(0, 40),
                    };
                }
                """)
                if d and d.get("candidates"):
                    stat_data = d
                    break
            except Exception:
                continue
        result["stat_page"] = stat_data
        print(f"  body 샘플 (300자):")
        print(f"    {stat_data.get('body_sample', '')[:300]}")
        print(f"  통계 숫자 후보 {len(stat_data.get('candidates', []))}개:")
        for c in stat_data.get('candidates', [])[:15]:
            print(f"    num={c['num']:>6} label='{c['label'][:30]:<30}' cls={c['cls'][:30]}")

    # 4. "이웃블로그" 메뉴 → 진짜 URL
    print(f"\n[4] '이웃블로그' 메뉴 분석")
    page.goto(f"https://admin.blog.naver.com/{BLOG_ID}", timeout=15000)
    time.sleep(3)
    nb_menu = next((m for m in menus if "이웃" in m["text"] and m["href"]), None)
    if nb_menu:
        print(f"  메뉴 href: {nb_menu['href']}")
        if nb_menu["href"].startswith("http") and "#" not in nb_menu["href"][-3:]:
            page.goto(nb_menu["href"], timeout=15000)
            time.sleep(3)
            result["neighbor_url"] = page.url
            print(f"  진입 URL: {page.url}")
        else:
            # 좌표 클릭
            page.mouse.move(nb_menu["pos"][0] + 30, nb_menu["pos"][1] + 10)
            time.sleep(0.4)
            page.mouse.click(nb_menu["pos"][0] + 30, nb_menu["pos"][1] + 10)
            time.sleep(3)
            result["neighbor_url_after_click"] = page.url
            print(f"  클릭 후 URL: {page.url}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 저장: {OUTPUT.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
