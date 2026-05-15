"""EUM 사이트 업무 페이지 탐색 스크립트.

탐색 대상:
- 단말기고장신고내역 (URL 미확인)
- WEBMAN382M00 단말기철거 (접근 재확인)
- WEBMAN400M00 단말기별이력관리 (구조 확인)
- 기타 미확인 페이지
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)

TARGET_PAGES = [
    ("WEBMAN370M00", "/web/man/WEBMAN370M00", "설치안내대상"),
    ("WEBMAN380M00", "/web/man/WEBMAN380M00", "현장별단말기목록"),
    ("WEBMAN381M00", "/web/man/WEBMAN381M00", "단말기설치계획"),
    ("WEBMAN382M00", "/web/man/WEBMAN382M00", "단말기철거"),
    ("WEBMAN390M00", "/web/man/WEBMAN390M00", "단말기설치현황"),
    ("WEBMAN400M00", "/web/man/WEBMAN400M00", "단말기별이력관리"),
    # 고장신고 관련 추정 ID
    ("WEBMAN410M00", "/web/man/WEBMAN410M00", "추정-고장신고"),
    ("WEBMAN420M00", "/web/man/WEBMAN420M00", "추정-고장신고2"),
    ("WEBMAN430M00", "/web/man/WEBMAN430M00", "추정-기타"),
    ("WEBMAN440M00", "/web/man/WEBMAN440M00", "추정-기타2"),
    ("WEBMAN450M00", "/web/man/WEBMAN450M00", "추정-기타3"),
    ("WEBMAN460M00", "/web/man/WEBMAN460M00", "추정-기타4"),
    ("WEBMAN470M00", "/web/man/WEBMAN470M00", "추정-기타5"),
    ("WEBMAN500M00", "/web/man/WEBMAN500M00", "추정-고장신고"),
    ("WEBMAN510M00", "/web/man/WEBMAN510M00", "추정-기타6"),
]


def extract_page_info(page) -> dict:
    """페이지 구조 추출 (폼, 버튼, 테이블, 입력 요소 포함)."""
    try:
        result = page.evaluate("""
        (() => {
            const url = window.location.href;
            const title = document.title;

            // 헤더/타이틀 추출
            const headings = Array.from(document.querySelectorAll('h1, h2, h3, .page-title, .tit, .title'))
                .slice(0, 5)
                .map(h => (h.innerText || '').trim().substring(0, 100))
                .filter(t => t.length > 0);

            // 폼 요소 추출
            const inputs = Array.from(document.querySelectorAll('input, select, textarea'))
                .filter(el => el.type !== 'hidden')
                .slice(0, 20)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.tagName === 'SELECT' ? Array.from(el.options).slice(0, 5).map(o => o.text).join(', ') : (el.value || ''),
                }));

            // 버튼 추출
            const buttons = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a.btn, .btn'))
                .slice(0, 20)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    text: (el.innerText || el.value || '').trim().substring(0, 50),
                    id: el.id || '',
                    classes: el.className ? el.className.substring(0, 80) : '',
                }))
                .filter(b => b.text.length > 0);

            // 테이블 컬럼 추출
            const tables = Array.from(document.querySelectorAll('table')).slice(0, 3).map(tbl => {
                const headers = Array.from(tbl.querySelectorAll('th')).map(th => (th.innerText || '').trim()).filter(t => t);
                const rowCount = tbl.querySelectorAll('tbody tr').length;
                return { headers: headers.slice(0, 15), rowCount };
            });

            // 접근 제한 감지
            const bodyText = document.body ? document.body.innerText : '';
            const isRestricted = bodyText.includes('접근') && (bodyText.includes('제한') || bodyText.includes('권한') || bodyText.includes('허용'));
            const isError = bodyText.includes('오류') || bodyText.includes('error') || bodyText.includes('404');

            // 메뉴/탭 링크 추출 (같은 도메인)
            const menuLinks = Array.from(document.querySelectorAll('a[href*="WEBMAN"], a[href*="web/man"]'))
                .map(a => ({ text: (a.innerText || '').trim(), href: a.getAttribute('href') }))
                .filter(l => l.text.length > 0)
                .slice(0, 20);

            return {
                url, title, headings, inputs, buttons, tables,
                isRestricted, isError,
                menuLinks,
                bodyPreview: bodyText.substring(0, 200),
            };
        })();
        """)
        return result
    except Exception as e:
        return {"error": str(e), "url": "", "title": ""}


def explore_pages():
    """각 페이지를 순서대로 탐색하고 결과 출력."""
    page = get_page()
    results = {}

    # 먼저 390 페이지로 이동해 로그인 상태 확인
    print("\n[1/2] 로그인 상태 확인 (WEBMAN390M00)...")
    page.goto("https://eum.cw.or.kr/web/man/WEBMAN390M00", timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    current_url = page.url
    if "login" in current_url.lower() or "signin" in current_url.lower():
        print("  ⚠ 로그인 필요 — CDP 브라우저에 로그인 세션이 없습니다.")
        print("  힌트: cdp_daemon.py로 브라우저 실행 후 수동 로그인 필요")
        return {}

    print(f"  ✓ 로그인 상태 OK (현재 URL: {current_url})")

    # 메뉴에서 실제 링크 수집
    print("\n[2/2] 메뉴 링크 수집...")
    menu_links = page.evaluate("""
    (() => {
        return Array.from(document.querySelectorAll('a[href]'))
            .filter(a => {
                const href = a.getAttribute('href') || '';
                return href.includes('WEBMAN') || href.includes('web/man');
            })
            .map(a => ({
                text: (a.innerText || '').trim().substring(0, 60),
                href: a.getAttribute('href'),
            }))
            .filter(l => l.text.length > 0);
    })();
    """)

    if menu_links:
        print(f"  메뉴 링크 {len(menu_links)}개 발견:")
        seen = set()
        for link in menu_links:
            href = link['href']
            if href not in seen:
                seen.add(href)
                print(f"    - {link['text']}: {href}")

    print("\n" + "=" * 60)
    print("각 페이지 탐색 시작")
    print("=" * 60)

    for page_id, path, label in TARGET_PAGES:
        url = f"https://eum.cw.or.kr{path}"
        print(f"\n[{page_id}] {label}")
        print(f"  URL: {url}")

        try:
            page.goto(url, timeout=20000)
            page.wait_for_load_state("domcontentloaded")
            time.sleep(1.5)

            info = extract_page_info(page)

            final_url = info.get("url", page.url)
            title = info.get("title", "")
            headings = info.get("headings", [])
            inputs = info.get("inputs", [])
            buttons = info.get("buttons", [])
            tables = info.get("tables", [])
            is_restricted = info.get("isRestricted", False)
            is_error = info.get("isError", False)
            menu_links_found = info.get("menuLinks", [])

            print(f"  실제 URL: {final_url}")
            print(f"  타이틀: {title}")

            if is_restricted:
                print("  ⛔ 접근 제한")
            elif is_error:
                print("  ✗ 오류 페이지")
            elif "login" in final_url.lower():
                print("  ⚠ 로그인 페이지로 리다이렉트")
            else:
                print(f"  ✓ 접근 가능")

            if headings:
                print(f"  헤딩: {' | '.join(headings[:3])}")

            if inputs:
                print(f"  입력 요소 ({len(inputs)}개):")
                for inp in inputs[:8]:
                    desc = f"{inp['tag']}[{inp['type']}]"
                    if inp['name']:
                        desc += f" name={inp['name']}"
                    if inp['placeholder']:
                        desc += f" placeholder='{inp['placeholder']}'"
                    if inp['value']:
                        desc += f" options=[{inp['value'][:60]}]"
                    print(f"    - {desc}")

            if buttons:
                btn_texts = [b['text'] for b in buttons if b['text']]
                print(f"  버튼: {' | '.join(btn_texts[:10])}")

            if tables:
                for i, tbl in enumerate(tables[:2]):
                    if tbl['headers']:
                        print(f"  테이블{i+1} 컬럼({tbl['rowCount']}행): {' | '.join(tbl['headers'][:10])}")

            if menu_links_found:
                seen_hrefs = set()
                unique = []
                for ml in menu_links_found:
                    if ml['href'] not in seen_hrefs:
                        seen_hrefs.add(ml['href'])
                        unique.append(ml)
                if unique:
                    print(f"  사이드메뉴 링크: {', '.join([m['text'] for m in unique[:8]])}")

            results[page_id] = {
                "url": final_url,
                "label": label,
                "title": title,
                "accessible": not is_restricted and not is_error and "login" not in final_url.lower(),
                "input_count": len(inputs),
                "button_count": len(buttons),
                "table_count": len(tables),
                "inputs": inputs,
                "buttons": buttons,
                "tables": tables,
            }

        except Exception as e:
            print(f"  ✗ 탐색 실패: {e}")
            results[page_id] = {"url": url, "label": label, "error": str(e)}

    return results


def print_summary(results: dict):
    """탐색 결과 요약 출력."""
    print("\n" + "=" * 60)
    print("탐색 결과 요약")
    print("=" * 60)

    accessible = [(pid, r) for pid, r in results.items() if r.get("accessible")]
    restricted = [(pid, r) for pid, r in results.items() if not r.get("accessible") and not r.get("error")]
    errors = [(pid, r) for pid, r in results.items() if r.get("error")]

    print(f"\n접근 가능 페이지 ({len(accessible)}개):")
    for pid, r in accessible:
        label = r.get("label", "")
        inputs = r.get("input_count", 0)
        buttons = r.get("button_count", 0)
        tables = r.get("table_count", 0)
        print(f"  ✓ {pid} ({label}): 입력{inputs} 버튼{buttons} 테이블{tables}")

    if restricted:
        print(f"\n접근 제한 페이지 ({len(restricted)}개):")
        for pid, r in restricted:
            print(f"  ⛔ {pid} ({r.get('label', '')})")

    if errors:
        print(f"\n오류/미존재 페이지 ({len(errors)}개):")
        for pid, r in errors:
            print(f"  ✗ {pid} ({r.get('label', '')}): {r.get('error', '')[:60]}")


if __name__ == "__main__":
    results = explore_pages()
    if results:
        print_summary(results)
    else:
        print("\n탐색 결과 없음 (로그인 필요 또는 연결 오류)")
