"""eum.cw.or.kr 사이트 전체 탐색 및 사이트맵 생성."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)

SITEMAP_DIR = Path("data/sitemap")
SITEMAP_DIR.mkdir(exist_ok=True)

def extract_page_structure(page) -> dict[str, Any]:
    """현재 페이지의 구조 추출."""
    try:
        result = page.evaluate("""
        (() => {
            return {
                url: window.location.href,
                title: document.title,
                headings: Array.from(document.querySelectorAll('h1, h2, h3'))
                    .slice(0, 10)
                    .map(h => ({level: h.tagName, text: (h.innerText || '').substring(0, 100)})),
                links: Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => {
                        const href = a.getAttribute('href') || '';
                        // 내부 링크만 포함 (# 제외, 외부 사이트 제외)
                        return href && !href.startsWith('#') && !href.startsWith('http');
                    })
                    .slice(0, 20)
                    .map(a => ({
                        text: (a.innerText || '').substring(0, 50).trim(),
                        href: a.getAttribute('href'),
                    })),
                tables: document.querySelectorAll('table').length,
                forms: document.querySelectorAll('form').length,
            };
        })();
        """)
        return result
    except Exception as e:
        _log.error("[explore-eum] 페이지 구조 추출 실패: %s", e)
        return {}


def build_sitemap():
    """사이트맵 구성."""
    sitemap = {
        "site": "eum.cw.or.kr",
        "root": "https://eum.cw.or.kr/main",
        "generated_at": str(__import__('datetime').datetime.now()),
        "pages": [],
        "navigation": {},
    }

    try:
        page = get_page()

        # 메인 페이지
        _log.info("[explore-eum] 메인 페이지 탐색 중...")
        page.goto("https://eum.cw.or.kr/main", timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        # 메인 페이지 구조
        main_page = extract_page_structure(page)
        sitemap["pages"].append({
            "path": "/main",
            "title": main_page.get("title"),
            "url": main_page.get("url"),
            "structure": {
                "headings": main_page.get("headings", []),
                "internal_links": main_page.get("links", []),
                "tables": main_page.get("tables", 0),
                "forms": main_page.get("forms", 0),
            }
        })

        # 주요 메뉴 탐색
        menu_items = page.evaluate("""
        (() => {
            // 주메뉴 찾기
            const gnb = document.querySelector('#gnb, nav, .nav, .navbar');
            if (!gnb) return [];

            const items = Array.from(gnb.querySelectorAll('a, li, button'))
                .filter(el => {
                    const text = el.innerText || '';
                    return text.trim().length > 0 && text.length < 50;
                })
                .map(el => {
                    const href = el.getAttribute('href') || '#';
                    const text = (el.innerText || '').substring(0, 50).trim();
                    return { text, href };
                })
                .filter((item, idx, arr) => arr.findIndex(x => x.text === item.text) === idx)
                .slice(0, 15);

            return items;
        })();
        """)

        _log.info("[explore-eum] 주요 메뉴 %d개 감지", len(menu_items))
        sitemap["navigation"]["main_menu"] = menu_items

        # 각 메뉴 아이템 탐색 (최대 5개)
        for idx, menu_item in enumerate(menu_items[:5]):
            href = menu_item.get("href", "#")
            text = menu_item.get("text", "")

            # 내부 링크인 경우만 탐색
            if href.startswith("#") or href.startswith("http"):
                continue

            _log.info("[explore-eum] 메뉴 %d/%d 탐색: %s", idx + 1, len(menu_items[:5]), text)

            try:
                full_url = f"https://eum.cw.or.kr{href}" if not href.startswith("http") else href
                page.goto(full_url, timeout=20000)
                page.wait_for_load_state("domcontentloaded")
                
                page_info = extract_page_structure(page)
                sitemap["pages"].append({
                    "path": href,
                    "title": page_info.get("title"),
                    "menu_text": text,
                    "url": page_info.get("url"),
                    "structure": {
                        "headings": page_info.get("headings", []),
                        "internal_links": page_info.get("links", []),
                        "tables": page_info.get("tables", 0),
                        "forms": page_info.get("forms", 0),
                    }
                })
            except Exception as e:
                _log.warning("[explore-eum] 메뉴 탐색 실패: %s - %s", text, e)

        # 사이트맵 저장
        sitemap_file = SITEMAP_DIR / "eum.cw.or.kr_sitemap.json"
        with open(sitemap_file, "w", encoding="utf-8") as f:
            json.dump(sitemap, f, ensure_ascii=False, indent=2)

        _log.info("[explore-eum] 사이트맵 저장 완료: %s", sitemap_file)
        print(f"\n✓ 사이트맵 저장 완료")
        print(f"  파일: {sitemap_file}")
        print(f"  페이지: {len(sitemap['pages'])}개")
        print(f"  메뉴: {len(menu_items)}개")

        return sitemap

    except Exception as e:
        _log.error("[explore-eum] 사이트맵 생성 실패: %s", e)
        print(f"✗ 사이트맵 생성 실패: {e}")
        raise


if __name__ == "__main__":
    build_sitemap()
