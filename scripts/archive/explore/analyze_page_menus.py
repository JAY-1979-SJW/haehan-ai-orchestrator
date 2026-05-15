"""현재 페이지의 메뉴 구조 분석."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger

_log = get_logger(__name__)

def analyze_menus_on_current_page():
    """현재 페이지의 메뉴 구조 분석."""
    try:
        import json
        from scripts.navigator import goto
        from playwright.sync_api import sync_playwright
        from scripts.cdp_daemon_client import get_cdp_page

        # CDP 브라우저에서 현재 페이지 가져오기
        page = get_cdp_page()
        
        # 메뉴 분석
        menus = page.evaluate("""
        (() => {
            // 주요 메뉴 영역 찾기
            const menuAreas = {
                top_menus: [],
                side_menus: [],
                footer_links: [],
            };

            // 상단 메뉴 (주로 span, a, button으로 이루어짐)
            const topMenuButtons = document.querySelectorAll('.gnb a, [class*="menu"] a, .nav a');
            topMenuButtons.forEach(el => {
                const text = (el.innerText || '').trim();
                if (text && text.length > 0 && text.length < 50) {
                    menuAreas.top_menus.push({
                        text,
                        href: el.getAttribute('href') || '',
                        class: el.className,
                    });
                }
            });

            // 사이드 메뉴
            const sideMenus = document.querySelectorAll('[class*="side"] a, [class*="lnb"] a');
            sideMenus.forEach(el => {
                const text = (el.innerText || '').trim();
                if (text && text.length > 0) {
                    menuAreas.side_menus.push({
                        text,
                        href: el.getAttribute('href') || '',
                    });
                }
            });

            // 주요 섹션/탭 찾기
            const sections = Array.from(document.querySelectorAll('h2, h1, [role="tab"], [class*="tab"]'))
                .slice(0, 20)
                .map(el => ({
                    text: (el.innerText || '').substring(0, 50).trim(),
                    tag: el.tagName,
                }))
                .filter(s => s.text.length > 0);

            return {
                ...menuAreas,
                sections,
                page_title: document.title,
                url: window.location.href,
            };
        })();
        """)

        print("\n[현재 페이지 메뉴 분석]")
        print(f"URL: {menus['url']}")
        print(f"제목: {menus['page_title']}")
        
        print(f"\n상단 메뉴 ({len(menus['top_menus'])}개):")
        for menu in menus['top_menus'][:15]:
            print(f"  - {menu['text']} → {menu['href']}")

        if menus['side_menus']:
            print(f"\n사이드 메뉴 ({len(menus['side_menus'])}개):")
            for menu in menus['side_menus'][:10]:
                print(f"  - {menu['text']} → {menu['href']}")

        print(f"\n주요 섹션 ({len(menus['sections'])}개):")
        for section in menus['sections'][:10]:
            print(f"  - {section['text']} ({section['tag']})")

        # 사이트맵에 저장
        sitemap = {
            "site": "eum.cw.or.kr",
            "url": menus['url'],
            "title": menus['page_title'],
            "structure": menus,
        }

        sitemap_file = ROOT / "data" / "sitemap" / "eum.cw.or.kr_menus.json"
        with open(sitemap_file, "w", encoding="utf-8") as f:
            json.dump(sitemap, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 메뉴 분석 결과 저장: {sitemap_file}")

    except ImportError as e:
        _log.warning("[analyze-menus] CDP 클라이언트 불가능: %s", e)
        print("✗ CDP 클라이언트 모듈 로드 실패")
    except Exception as e:
        _log.error("[analyze-menus] 메뉴 분석 실패: %s", e)
        print(f"✗ 메뉴 분석 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_menus_on_current_page()
