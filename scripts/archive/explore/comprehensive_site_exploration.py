"""건설근로자공제회 전체 사이트 체계적 탐색
- 모든 메뉴/서브메뉴 찾기
- 각 섹션에서 단말기 관련 정보 파악
- 통계/대시보드 정보 수집
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def explore_site_structure() -> dict:
    """사이트 전체 구조 탐색"""
    page = get_page()

    # 메인 페이지부터 시작
    main_url = "https://eum.cw.or.kr/main"
    _log.info(f"[탐색 시작] {main_url}")
    try:
        page.goto(main_url, timeout=30000)
        page.wait_for_load_state("load", timeout=5000)
    except Exception as e:
        _log.warning(f"메인 페이지 로드 실패: {e}, 관리 페이지로 계속")
        pass

    # 팝업 처리
    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    exploration = {
        "site": "eum.cw.or.kr",
        "main_navigation": [],
        "all_pages": [],
        "sections": {}
    }

    # 1. 메인 네비게이션 메뉴 파악
    print("\n" + "="*80)
    print("[1단계] 메인 네비게이션 메뉴 파악")
    print("="*80)

    nav_result = page.evaluate("""
    (() => {
        const menus = [];

        // 주요 메뉴 찾기
        const mainNav = document.querySelector('nav') || document.querySelector('header');
        if (mainNav) {
            const links = mainNav.querySelectorAll('a');
            links.forEach(a => {
                const href = a.href || '';
                const text = a.innerText?.trim() || '';

                if (text && !text.includes('로그인')) {
                    menus.push({
                        text: text,
                        href: href,
                        isExternal: !href.includes('eum.cw.or.kr')
                    });
                }
            });
        }

        return {
            menus: menus.slice(0, 20),
            count: menus.length
        };
    })();
    """)

    for menu in nav_result['menus']:
        if menu['href'] and 'eum.cw.or.kr' in menu['href']:
            print(f"  • {menu['text']:<20} → {menu['href']}")
            exploration['main_navigation'].append(menu)

    # 2. 마이페이지 탐색 (로그인 후 접근 가능한 모든 메뉴)
    print("\n" + "="*80)
    print("[2단계] 마이페이지 및 관리 섹션 탐색")
    print("="*80)

    mypage_url = "https://eum.cw.or.kr/mypage"
    page.goto(mypage_url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    mypage_info = page.evaluate("""
    (() => {
        const sections = [];

        // 좌측 메뉴 (사이드바) 찾기
        const sidebar = document.querySelector('.sidebar') ||
                       document.querySelector('.lnb') ||
                       document.querySelector('[class*="menu"]');

        if (sidebar) {
            const items = sidebar.querySelectorAll('a, li');
            items.forEach(item => {
                const text = item.innerText?.trim() || '';
                const href = item.href || item.querySelector('a')?.href || '';

                if (text && text.length > 1 && text.length < 100) {
                    sections.push({
                        text: text,
                        href: href
                    });
                }
            });
        }

        // 또는 메인 content에서 메뉴 찾기
        const mainMenu = document.querySelector('main') || document.body;
        const menuLinks = mainMenu.querySelectorAll('a[href*="/web/"]');

        const uniqueLinks = new Map();
        menuLinks.forEach(link => {
            const href = link.href || '';
            const text = link.innerText?.trim() || '';
            if (href && !uniqueLinks.has(href)) {
                uniqueLinks.set(href, text);
            }
        });

        return {
            sidebarItems: sections.slice(0, 30),
            webLinks: Array.from(uniqueLinks.entries()).map(([href, text]) => ({
                text: text || '(제목없음)',
                href: href
            }))
        };
    })();
    """)

    print(f"\n[마이페이지 메뉴 항목]")
    for item in mypage_info['sidebarItems'][:15]:
        if item['text']:
            print(f"  • {item['text']:<30}")

    print(f"\n[/web/ 페이지 링크 ({len(mypage_info['webLinks'])}개)]")
    web_links_by_category = {}
    for link in mypage_info['webLinks']:
        if link['href']:
            # URL에서 카테고리 추출 (e.g., /web/man/ → 관리)
            parts = link['href'].split('/')
            if len(parts) > 3:
                category = parts[3]  # /web/XXX/
                if category not in web_links_by_category:
                    web_links_by_category[category] = []
                web_links_by_category[category].append(link)

    for category, links in sorted(web_links_by_category.items()):
        print(f"\n  [{category.upper()}] {len(links)}개 페이지")
        for link in links[:5]:
            print(f"    • {link['text'][:50]}")
        if len(links) > 5:
            print(f"    ... 외 {len(links)-5}개")

    # 3. 관리(man) 섹션 상세 탐색
    print("\n" + "="*80)
    print("[3단계] 관리(MAN) 섹션 상세 탐색")
    print("="*80)

    manage_url = "https://eum.cw.or.kr/manage"
    page.goto(manage_url, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=10000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    manage_menus = page.evaluate("""
    (() => {
        const allLinks = document.querySelectorAll('a[href*="/web/man/"]');
        const links = [];

        allLinks.forEach(a => {
            const href = a.href || '';
            const text = a.innerText?.trim() || '';

            if (href && text && text.length > 1 && text.length < 100) {
                links.push({ text, href });
            }
        });

        // 중복 제거
        const unique = new Map();
        links.forEach(l => {
            if (!unique.has(l.href)) {
                unique.set(l.href, l);
            }
        });

        return Array.from(unique.values());
    })();
    """)

    print(f"\n[관리 페이지 목록] ({len(manage_menus)}개)")
    for i, link in enumerate(manage_menus[:20], 1):
        # URL에서 페이지 ID 추출
        page_id = link['href'].split('/')[-1] if '/' in link['href'] else ''
        print(f"  {i:2}. {link['text']:<40} | {page_id}")

    if len(manage_menus) > 20:
        print(f"  ... 외 {len(manage_menus)-20}개")

    # 4. 단말기 관련 페이지들 중점 탐색
    print("\n" + "="*80)
    print("[4단계] 단말기 관련 페이지 상세 분석")
    print("="*80)

    device_pages = [
        ("WEBMAN380M00", "단말기 관리"),
        ("WEBMAN390M00", "기타 관리"),
    ]

    device_info = {}
    for page_id, name in device_pages:
        url = f"https://eum.cw.or.kr/web/man/{page_id}"
        print(f"\n  [{name}] {url}")

        try:
            page.goto(url, timeout=30000)
            page.wait_for_load_state("load", timeout=5000)

            try:
                from scripts.popup_detector import handle_page_popups
                handle_page_popups(page, timeout_s=2.0)
            except:
                pass

            page_data = page.evaluate(f"""
            (() => {{
                return {{
                    pageTitle: document.title,
                    hasTable: !!document.querySelector('table'),
                    tableRows: document.querySelectorAll('table tbody tr').length,
                    hasForm: !!document.querySelector('form'),
                    stats: Array.from(document.querySelectorAll('[class*="stat"], [class*="count"], [class*="total"]'))
                        .map(e => e.innerText?.trim()).filter(t => t),
                    filters: Array.from(document.querySelectorAll('select'))
                        .map(s => ({
                            name: s.name || s.id,
                            optionCount: s.options.length
                        }))
                }};
            }})();
            """)

            device_info[name] = page_data
            print(f"    ✓ 테이블: {'있음' if page_data['hasTable'] else '없음'}")
            if page_data['hasTable']:
                print(f"      행 수: {page_data['tableRows']}개")
            if page_data['stats']:
                print(f"      통계: {', '.join(page_data['stats'][:3])}")

        except Exception as e:
            _log.debug(f"페이지 탐색 오류: {e}")

    # 5. 대시보드 페이지 확인
    print("\n" + "="*80)
    print("[5단계] 대시보드/통계 페이지 탐색")
    print("="*80)

    dashboard_candidates = [
        "https://eum.cw.or.kr/web/com/WEBCOM010P03",  # 알림 페이지
        "https://eum.cw.or.kr/mypage",  # 마이페이지
    ]

    for dashboard_url in dashboard_candidates:
        try:
            page.goto(dashboard_url, timeout=30000)
            page.wait_for_load_state("load", timeout=5000)

            try:
                from scripts.popup_detector import handle_page_popups
                handle_page_popups(page, timeout_s=2.0)
            except:
                pass

            dashboard_data = page.evaluate("""
            (() => {
                const stats = {};

                // 숫자가 큰 텍스트 찾기 (통계 정보)
                const texts = Array.from(document.querySelectorAll('*'))
                    .map(e => e.innerText?.trim())
                    .filter(t => t && /\\d{2,}/.test(t) && t.length < 50);

                return {
                    url: document.location.pathname,
                    title: document.title,
                    potentialStats: texts.slice(0, 10)
                };
            })();
            """)

            print(f"\n  [{dashboard_data['title']}]")
            if dashboard_data['potentialStats']:
                print(f"    통계 정보: {dashboard_data['potentialStats'][:5]}")

        except Exception as e:
            _log.debug(f"대시보드 탐색 오류: {e}")

    exploration['device_pages'] = device_info
    exploration['web_links_summary'] = web_links_by_category

    return exploration


if __name__ == "__main__":
    try:
        result = explore_site_structure()

        # 결과 저장
        output_file = Path("data") / "site_structure_exploration.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

        print("\n" + "="*80)
        print("✓ 사이트 탐색 완료")
        print(f"✓ 결과 저장: {output_file}")
        print("="*80 + "\n")

    except Exception as e:
        _log.error(f"탐색 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
