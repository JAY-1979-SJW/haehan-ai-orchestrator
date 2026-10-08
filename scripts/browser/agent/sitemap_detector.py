"""사이트 맵 자동 탐지 — robots.txt, sitemap.xml, API 엔드포인트."""

from __future__ import annotations

import contextlib
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SitemapInfo:
    """사이트 맵 정보."""

    domain: str
    robots_txt: str | None = None
    sitemap_url: str | None = None
    api_endpoints: list[str] | None = None
    page_structure: dict | None = None
    selectors: dict | None = None  # {element_type: [selectors]}

    def __post_init__(self):
        if self.api_endpoints is None:
            self.api_endpoints = []
        if self.page_structure is None:
            self.page_structure = {}
        if self.selectors is None:
            self.selectors = {}


def fetch_robots_txt(domain: str, timeout: float = 5.0) -> str | None:
    """robots.txt 다운로드."""
    try:
        url = f"https://{domain}/robots.txt"
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
        return None


def extract_sitemap_url(robots_txt: str) -> str | None:
    """robots.txt에서 sitemap URL 추출."""
    match = re.search(r"Sitemap:\s*(\S+)", robots_txt, re.IGNORECASE)
    return match.group(1) if match else None


def fetch_sitemap_xml(sitemap_url: str, timeout: float = 5.0) -> str | None:
    """sitemap.xml 다운로드."""
    try:
        with urllib.request.urlopen(sitemap_url, timeout=timeout) as r:  # noqa: S310
            return r.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
        return None


def extract_urls_from_sitemap(sitemap_xml: str) -> list[str]:
    """sitemap.xml에서 URL 목록 추출."""
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)
    return urls


def detect_api_endpoints(page_html: str, domain: str) -> list[str]:
    """페이지 HTML에서 API 엔드포인트 탐지."""
    endpoints = set()

    # 1. XHR 요청 탐지 (JavaScript fetch/XMLHttpRequest)
    api_patterns = [
        r"fetch\(['\"]([^'\"]+)['\"]",  # fetch('/api/...')
        r"\.get\(['\"]([^'\"]+)['\"]",  # .get('/api/...')
        r"\.post\(['\"]([^'\"]+)['\"]",  # .post('/api/...')
        r"/api/[a-z0-9/_-]+",  # /api/v1/...
        r"/v[0-9]+/[a-z0-9/_-]+",  # /v2/...
    ]

    for pattern in api_patterns:
        matches = re.findall(pattern, page_html)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            if match.startswith("/"):
                endpoints.add(match)
            elif domain in match:
                # 절대 URL
                endpoints.add("/" + match.split(domain)[-1])

    return sorted(list(endpoints))


def detect_selectors_by_network(page) -> dict[str, list[str]]:
    """Playwright 페이지에서 네트워크 요청 분석하여 API 엔드포인트 탐지."""
    with contextlib.suppress(Exception):
        # Network 요청 히스토리는 직접 접근 불가하므로
        # page.evaluate로 JavaScript에서 추출
        pass

    return {}


def detect_dom_selectors(page) -> dict[str, list[dict[str, object]]]:
    """DOM에서 주요 셀렉터 자동 탐지."""
    selectors_result: dict[str, list[dict[str, object]]] = {}

    try:
        # 메일 아이템 셀렉터 탐지
        mail_selectors = [
            "li[data-mailsn]",
            "tr.mail_list",
            ".mailListItem",
            '[role="listitem"]',
            "div[data-mail-id]",
            'a[href*="/read/"]',
            ".mail_item",
            '[class*="mail"][class*="item"]',
        ]

        mail_found = []
        for sel in mail_selectors:
            try:
                count = len(page.query_selector_all(sel))
                if count > 0:
                    mail_found.append({"selector": sel, "count": count})
            except:  # noqa: S110, E722
                pass

        if mail_found:
            selectors_result["mail_item"] = mail_found

        # 폴더 셀렉터 탐지
        folder_selectors = [
            '[class*="folder"]',
            '[class*="nav"]',
            'ul[class*="list"]',
            'div[role="navigation"]',
        ]

        folder_found = []
        for sel in folder_selectors:
            try:
                count = len(page.query_selector_all(sel))
                if count > 0:
                    folder_found.append({"selector": sel, "count": count})
            except:  # noqa: S110, E722
                pass

        if folder_found:
            selectors_result["folder"] = folder_found

        return selectors_result

    except Exception as e:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
        print(f"  ✗ DOM 셀렉터 탐지 실패: {e}")
        return {}


def detect_page_structure(page) -> dict:
    """페이지 구조 자동 탐지."""
    try:
        structure = page.evaluate(
            """() => {
            return {
                url: window.location.href,
                title: document.title,
                isDynamic: typeof __INITIAL_STATE__ !== 'undefined' || typeof window.__data !== 'undefined',
                hasIframe: document.querySelectorAll('iframe').length > 0,
                mainContent: {
                    lists: document.querySelectorAll('[class*="list"], ul, ol').length,
                    forms: document.querySelectorAll('form, input').length,
                    buttons: document.querySelectorAll('button, [role="button"]').length,
                    links: document.querySelectorAll('a[href]').length,
                },
            };
        }"""
        )
        return structure
    except Exception:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
        return {}


def detect_sitemap(domain: str, page=None) -> SitemapInfo:
    """전체 사이트 맵 탐지."""
    print(f"\n📍 사이트 맵 탐지: {domain}")
    info = SitemapInfo(domain=domain)

    # 1. robots.txt
    print("  1️⃣  robots.txt 다운로드...", end=" ", flush=True)
    robots_txt = fetch_robots_txt(domain)
    if robots_txt:
        info.robots_txt = robots_txt[:500]  # 처음 500자만 저장
        print(f"✓ ({len(robots_txt)}bytes)")
    else:
        print("✗")

    # 2. sitemap.xml
    if robots_txt:
        print("  2️⃣  sitemap.xml URL 추출...", end=" ", flush=True)
        sitemap_url = extract_sitemap_url(robots_txt)
        if sitemap_url:
            info.sitemap_url = sitemap_url
            print(f"✓ {sitemap_url}")

            print("  3️⃣  sitemap.xml 다운로드...", end=" ", flush=True)
            sitemap_xml = fetch_sitemap_xml(sitemap_url)
            if sitemap_xml:
                urls = extract_urls_from_sitemap(sitemap_xml)
                print(f"✓ ({len(urls)} URLs)")
        else:
            print("✗")

    # 3. API 엔드포인트 (HTML 분석)
    if page:
        print("  4️⃣  페이지 구조 탐지...", end=" ", flush=True)
        try:
            structure = detect_page_structure(page)
            info.page_structure = structure
            print(f"✓ (동적={structure.get('isDynamic', False)})")
        except Exception as e:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
            print(f"✗ {e}")

        # 4. DOM 셀렉터
        print("  5️⃣  DOM 셀렉터 탐지...", end=" ", flush=True)
        try:
            selectors = detect_dom_selectors(page)
            info.selectors = selectors
            print(f"✓ ({len(selectors)} 타입)")
        except Exception as e:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
            print(f"✗ {e}")

        # 5. API 엔드포인트 (HTML 분석)
        print("  6️⃣  API 엔드포인트 탐지...", end=" ", flush=True)
        try:
            page_html = page.content()
            endpoints = detect_api_endpoints(page_html, domain)
            info.api_endpoints = endpoints[:20]  # 처음 20개만
            print(f"✓ ({len(endpoints)} endpoints)")
        except Exception as e:  # noqa: BLE001 - 사이트 robots.txt/sitemap.xml/DOM 구조 읽기전용 탐지기 - 실패시 None 또는 빈 dict 반환, 쓰기 없음
            print(f"✗ {e}")

    return info


def save_sitemap_cache(info: SitemapInfo, cache_dir: Path | None = None):
    """사이트 맵 캐시 저장."""
    if cache_dir is None:
        cache_dir = Path(__file__).parent / ".sitemap_cache"

    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{info.domain.replace('.', '_')}.json"

    # SitemapInfo를 dict로 변환 (dataclass → dict)
    data = asdict(info)

    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  💾 캐시 저장: {cache_file}")
    return cache_file


def main():
    """테스트용 main."""
    from scripts.browser.agent.agent import BrowserAgent

    domains = [
        "mail.naver.com",
        "calendar.naver.com",
        "mybox.naver.com",
    ]

    print("\n" + "=" * 60)
    print("  사이트 맵 자동 탐지")
    print("=" * 60)

    for domain in domains:
        with BrowserAgent() as agent:
            url = f"https://{domain}/"
            print(f"\n🔗 {url}")
            agent.go(url)
            time.sleep(2)

            info = detect_sitemap(domain, page=agent._page)
            save_sitemap_cache(info)

            # 결과 출력
            print("\n  📊 결과:")
            print(f"    - Sitemap URL: {info.sitemap_url or '없음'}")
            print(f"    - API 엔드포인트: {len(info.api_endpoints)}")
            print(f"    - DOM 셀렉터: {list(info.selectors.keys())}")
            print(f"    - 페이지 구조: {info.page_structure}")

    print("\n" + "=" * 60)
    print("  완료")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
