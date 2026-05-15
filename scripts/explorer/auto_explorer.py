"""자동 사이트 탐색 — 로그인 후 메뉴/링크를 따라 사이트맵 생성.

원칙:
  - 같은 호스트만 (외부 사이트 보호)
  - 너비 우선 BFS, depth/budget 제한
  - 각 페이지에서: 제목, URL, 폼 발견, 데이터 테이블 발견, 링크 수집
  - 봇 감지 시 즉시 중단 (bot_radar 통합)
  - read-only — POST/form submit 금지

출력:
  data/sitemap/<host>_auto_<ts>.json
  {
    "host": "...",
    "started_url": "...",
    "pages": [{url, title, forms, tables, links_out}, ...],
    "bot_radar": {...},
  }

사용:
    from scripts.explorer.auto_explorer import explore_site
    r = explore_site(page, depth=2, max_pages=20)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urljoin

from scripts.logger import get_logger
from scripts.form.discovery import discover_form
from scripts.form.bot_radar import scan as bot_scan, BotDetected

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SITEMAP_DIR = ROOT / "data" / "sitemap"


def _same_host(a: str, b: str) -> bool:
    try:
        ua, ub = urlparse(a), urlparse(b)
        return (ua.hostname or "").lower() == (ub.hostname or "").lower()
    except Exception:
        return False


def _norm_url(href: str, base: str) -> str:
    try:
        return urljoin(base, href).split("#")[0]
    except Exception:
        return href


# 페이지에서 의미있는 메타 추출 JS
_PAGE_SUMMARY_JS = r"""
() => {
  // 링크 수집 (visible, 같은 사이트 추정)
  const links = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const r = a.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
    const txt = (a.innerText || a.textContent || '').trim().slice(0, 80);
    links.push({href, text: txt});
  });
  // 테이블 (데이터 있을 만한 곳)
  const tables = [];
  document.querySelectorAll('table').forEach((t, idx) => {
    const rows = t.querySelectorAll('tr').length;
    const cols = t.querySelector('tr') ? t.querySelector('tr').children.length : 0;
    if (rows > 1 && cols > 1) {
      const header = Array.from(t.querySelectorAll('tr:first-child th, tr:first-child td'))
                          .map(c => (c.innerText || '').trim().slice(0, 40));
      tables.push({idx, rows, cols, header});
    }
  });
  // 폼 개수 (간단)
  const forms = document.querySelectorAll('form').length;
  return {
    title: document.title || '',
    url: location.href,
    links, tables, forms,
  };
}
"""


def _page_summary(page) -> dict:
    try:
        s = page.evaluate(_PAGE_SUMMARY_JS)
        if isinstance(s, dict):
            return s
    except Exception as e:
        log.debug("[explorer] page_summary 실패: %s", e)
    return {"title": "", "url": "", "links": [], "tables": [], "forms": 0}


def explore_site(
    page,
    *,
    depth: int = 2,
    max_pages: int = 20,
    save: bool = True,
    same_host_only: bool = True,
    bot_check_each_page: bool = True,
    skip_url_patterns: tuple[str, ...] = (
        "logout", "signout", "delete", "remove", "submit",
    ),
) -> dict:
    """현재 페이지부터 BFS 탐색.

    Args:
        depth: 최대 깊이
        max_pages: 최대 방문 페이지 수 (budget)
        save: data/sitemap/<host>_auto_<ts>.json 저장 여부
        same_host_only: 같은 호스트만
        bot_check_each_page: 각 페이지에서 봇 레이더 스캔
        skip_url_patterns: 위험 URL 키워드 (로그아웃/삭제/제출 등 자동 회피)

    Returns:
        dict{host, started_url, pages, bot_radar, elapsed_s}
    """
    started_at = time.time()
    try:
        start_url = page.url or ""
    except Exception:
        start_url = ""
    host = urlparse(start_url).hostname or ""

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages_data: list[dict] = []
    bot_reports: list[dict] = []
    aborted_reason = ""

    log.info("[explorer] 시작 host=%s start=%s depth=%d max=%d",
             host, start_url, depth, max_pages)

    while queue and len(pages_data) < max_pages:
        url, d = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        # 위험 URL 회피
        if any(p in url.lower() for p in skip_url_patterns):
            log.info("[explorer] skip 위험 URL: %s", url)
            continue

        # 같은 호스트
        if same_host_only and host and not _same_host(start_url, url):
            log.debug("[explorer] skip 외부 호스트: %s", url)
            continue

        # 이동 (현재 URL과 다를 때만)
        try:
            cur = page.url or ""
        except Exception:
            cur = ""
        if cur != url:
            try:
                page.goto(url, timeout=20000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
            except Exception as e:
                log.warning("[explorer] goto 실패 %s: %s", url, e)
                pages_data.append({"url": url, "error": f"goto: {str(e)[:120]}"})
                continue

        # 봇 감지
        if bot_check_each_page:
            try:
                br = bot_scan(page)
                bot_reports.append({"url": url, "level": br["level"],
                                    "vendors": br["vendors"]})
                if br["flagged"]:
                    aborted_reason = f"bot_flagged: {br['level']}"
                    log.warning("[explorer] 봇 감지 — 중단: %s", aborted_reason)
                    break
            except Exception:
                pass

        # 페이지 요약
        s = _page_summary(page)
        # 폼 자동 탐색 (있으면)
        form_summary = {}
        if s.get("forms", 0) > 0:
            try:
                disc = discover_form(page)
                form_summary = {
                    "intent": disc.intent,
                    "roles": sorted({f.role for f in disc.fields if f.score > 0.4}),
                    "submit": disc.submit_selector,
                }
            except Exception:
                pass

        rec = {
            "url": url, "depth": d,
            "title": s.get("title", "")[:120],
            "tables": s.get("tables", [])[:10],
            "forms_count": s.get("forms", 0),
            "form_summary": form_summary,
            "links_out": [],
        }

        # 링크 수집 + 다음 큐
        out_links = []
        for link in s.get("links", []):
            nurl = _norm_url(link.get("href", ""), url)
            if not nurl.startswith(("http://", "https://")):
                continue
            if same_host_only and not _same_host(start_url, nurl):
                continue
            out_links.append({"href": nurl, "text": link.get("text", "")[:80]})
            if nurl not in visited and d + 1 <= depth:
                queue.append((nurl, d + 1))
        # 중복 제거
        seen = set()
        rec["links_out"] = [l for l in out_links
                            if not (l["href"] in seen or seen.add(l["href"]))][:50]

        pages_data.append(rec)
        log.info("[explorer] [%d/%d] d=%d %s — 링크 %d개",
                 len(pages_data), max_pages, d,
                 (s.get("title", "") or url)[:60], len(rec["links_out"]))

    elapsed = round(time.time() - started_at, 2)
    result = {
        "host": host,
        "started_url": start_url,
        "depth": depth,
        "max_pages": max_pages,
        "visited_count": len(pages_data),
        "elapsed_s": elapsed,
        "aborted_reason": aborted_reason,
        "pages": pages_data,
        "bot_reports": bot_reports[-30:],
    }

    if save and host:
        SITEMAP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
        fp = SITEMAP_DIR / f"{safe_host}_auto_{ts}.json"
        fp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        result["saved_to"] = str(fp)
        log.info("[explorer] 저장: %s", fp)

    return result
