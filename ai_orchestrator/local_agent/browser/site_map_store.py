"""사이트 맵 저장소 — 탐색 결과 저장 + 변화 감지 + 자동 재탐색.

흐름:
  1. 저장된 맵 로드
  2. 홈페이지 nav 해시 비교 (빠른 체크, ~3초)
  3. 변화 없으면 기존 맵 반환
  4. 변화 감지 시 재탐색 후 맵 갱신
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SITEMAP_DIR = Path(__file__).resolve().parents[3] / "data" / "sitemap"
MAX_PAGES    = 80    # 최대 탐색 페이지 수
MAX_DEPTH    = 3     # 최대 탐색 깊이
STALE_DAYS   = 30   # 강제 갱신 주기


# ── 데이터 구조 ───────────────────────────────────────────────

@dataclass
class PageInfo:
    url: str
    title: str
    depth: int
    links: list[str] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)   # {action, method, inputs:[name]}
    buttons: list[str] = field(default_factory=list)  # 버튼 텍스트 목록
    headings: list[str] = field(default_factory=list)


@dataclass
class SiteMap:
    domain: str
    home_url: str
    crawled_at: str = ""
    nav_hash: str = ""          # 변화 감지용 — 홈 nav 링크 해시
    page_count: int = 0
    pages: dict[str, dict] = field(default_factory=dict)   # url → PageInfo dict

    def save(self) -> Path:
        SITEMAP_DIR.mkdir(parents=True, exist_ok=True)
        safe = self.domain.replace(":", "_").replace("/", "_")
        path = SITEMAP_DIR / f"{safe}.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load(domain: str) -> "SiteMap | None":
        safe = domain.replace(":", "_").replace("/", "_")
        path = SITEMAP_DIR / f"{safe}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SiteMap(**data)
        except Exception:
            return None

    def is_stale(self) -> bool:
        if not self.crawled_at:
            return True
        try:
            crawled = datetime.fromisoformat(self.crawled_at)
            age = (datetime.now(timezone.utc) - crawled).days
            return age >= STALE_DAYS
        except Exception:
            return True

    def find_page(self, keyword: str) -> list[dict]:
        """키워드로 페이지 검색."""
        kw = keyword.lower()
        return [
            p for p in self.pages.values()
            if kw in p.get("url", "").lower() or kw in p.get("title", "").lower()
        ]

    def find_selector(self, keyword: str) -> list[str]:
        """키워드와 관련된 버튼/폼 정보 검색."""
        kw = keyword.lower()
        results = []
        for p in self.pages.values():
            for btn in p.get("buttons", []):
                if kw in btn.lower():
                    results.append(f"[버튼] '{btn}' @ {p['url']}")
            for form in p.get("forms", []):
                if kw in json.dumps(form, ensure_ascii=False).lower():
                    results.append(f"[폼] {form} @ {p['url']}")
        return results


# ── 해시 계산 ─────────────────────────────────────────────────

def _nav_hash(page: Any) -> str:
    """홈페이지 주요 nav 링크 목록의 MD5 해시."""
    try:
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('nav a, header a, .gnb a, #gnb a'))
                .map(a => a.href).filter(Boolean).sort()
        """)
        raw = "|".join(links)
        return hashlib.md5(raw.encode()).hexdigest()
    except Exception:
        return ""


# ── 단일 페이지 탐색 ──────────────────────────────────────────

PAGE_TIMEOUT   = 8000   # goto 타임아웃 (ms) — 20초에서 8초로 단축
EVAL_TIMEOUT   = 5000   # evaluate 타임아웃 (ms) — hang 방지


def _crawl_page(page: Any, url: str, domain: str, depth: int) -> PageInfo:
    # 페이지 이동 — 타임아웃 초과 시 빈 정보 반환하고 건너뜀
    try:
        page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
    except Exception:
        return PageInfo(url=url, title="", depth=depth)

    title = ""
    try:
        title = page.title()
    except Exception:
        pass

    # 내부 링크 — evaluate 타임아웃 추가, SPA(#링크) 포함
    links: list[str] = []
    try:
        raw = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href).filter(Boolean)
        """, timeout=EVAL_TIMEOUT)
        # SPA 지원: #링크도 포함하되 순수 # 앵커(같은 페이지)만 제외
        links = sorted(set(
            l for l in raw
            if domain in l and l != url
            and not l.endswith("#")
            and not l == url.split("#")[0] + "#"
        ))
    except Exception:
        pass

    # 폼
    forms: list[dict] = []
    try:
        forms = page.evaluate("""
            () => Array.from(document.querySelectorAll('form')).map(f => ({
                action: f.action || '',
                method: f.method || 'get',
                inputs: Array.from(f.querySelectorAll('input,select,textarea'))
                             .map(i => i.name || i.placeholder || i.type).filter(Boolean)
            }))
        """, timeout=EVAL_TIMEOUT)
    except Exception:
        pass

    # 버튼 텍스트
    buttons: list[str] = []
    try:
        buttons = page.evaluate("""
            () => Array.from(document.querySelectorAll('button,[role=button]'))
                .map(b => b.textContent.trim()).filter(t => t.length > 0 && t.length < 40)
        """, timeout=EVAL_TIMEOUT)
        buttons = list(dict.fromkeys(buttons))[:20]
    except Exception:
        pass

    # 헤딩
    headings: list[str] = []
    try:
        headings = page.evaluate("""
            () => Array.from(document.querySelectorAll('h1,h2,h3'))
                .map(h => h.textContent.trim()).filter(t => t.length > 0 && t.length < 60)
        """, timeout=EVAL_TIMEOUT)
        headings = list(dict.fromkeys(headings))[:10]
    except Exception:
        pass

    return PageInfo(url=url, title=title, depth=depth,
                    links=links, forms=forms, buttons=buttons, headings=headings)


# ── 재귀 크롤러 ───────────────────────────────────────────────

def crawl(page: Any, home_url: str, domain: str,
          max_depth: int = MAX_DEPTH, max_pages: int = MAX_PAGES,
          verbose: bool = True) -> SiteMap:
    """사이트를 재귀 탐색해서 SiteMap 반환."""
    sitemap = SiteMap(domain=domain, home_url=home_url)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(home_url, 0)]

    while queue and len(visited) < max_pages:
        url, depth = queue.pop(0)
        if url in visited or depth > max_depth:
            continue
        visited.add(url)

        if verbose:
            print(f"  [{len(visited):3d}] depth={depth} {url[:80]}")

        info = _crawl_page(page, url, domain, depth)
        sitemap.pages[url] = asdict(info)

        # 홈이면 nav 해시 계산
        if url == home_url:
            sitemap.nav_hash = _nav_hash(page)

        # 하위 링크 큐 추가
        if depth < max_depth:
            for link in info.links:
                if link not in visited:
                    queue.append((link, depth + 1))

    sitemap.page_count = len(sitemap.pages)
    sitemap.crawled_at = datetime.now(timezone.utc).isoformat()
    return sitemap


# ── 변화 감지 ─────────────────────────────────────────────────

def needs_recrawl(page: Any, sitemap: SiteMap, home_url: str) -> bool:
    """저장된 맵과 현재 nav 해시 비교 — 변화 감지 시 True."""
    if sitemap.is_stale():
        print("  → 맵이 오래됨 (30일 초과) → 재탐색")
        return True
    try:
        page.goto(home_url, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        current_hash = _nav_hash(page)
        if current_hash and current_hash != sitemap.nav_hash:
            print(f"  → 사이트 변화 감지 (nav 해시 변경) → 재탐색")
            return True
        return False
    except Exception:
        return False


# ── 통합 진입점 ───────────────────────────────────────────────

def ensure_sitemap(page: Any, home_url: str, domain: str,
                   force: bool = False, verbose: bool = True) -> SiteMap:
    """저장된 맵 로드 → 변화 감지 → 필요 시 재탐색 후 반환."""
    sitemap = SiteMap.load(domain)

    if sitemap and not force:
        if verbose:
            print(f"  저장된 맵 로드: {sitemap.page_count}페이지 ({sitemap.crawled_at[:10]})")
        if not needs_recrawl(page, sitemap, home_url):
            if verbose:
                print(f"  → 변화 없음 — 기존 맵 사용")
            return sitemap
    else:
        if verbose:
            reason = "강제 갱신" if force else "최초 탐색"
            print(f"  → {reason} 시작")

    # 재탐색
    if verbose:
        print(f"  재탐색 시작: {home_url}")
    sitemap = crawl(page, home_url, domain, verbose=verbose)
    path = sitemap.save()
    if verbose:
        print(f"  ✓ 맵 저장: {path} ({sitemap.page_count}페이지)")
    return sitemap
