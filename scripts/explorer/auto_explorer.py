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

import contextlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from scripts.form.bot_radar import scan as bot_scan
from scripts.form.discovery import discover_form
from scripts.common.logger import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SITEMAP_DIR = ROOT / "data" / "sitemap"


def _same_host(a: str, b: str) -> bool:
    try:
        ua, ub = urlparse(a), urlparse(b)
        return (ua.hostname or "").lower() == (ub.hostname or "").lower()
    except Exception:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
        return False


def _norm_url(href: str, base: str) -> str:
    try:
        return urljoin(base, href).split("#")[0]
    except Exception:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
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
  // 폼 없이 버튼·편집 영역으로만 동작하는 화면도 업무 화면이다(글쓰기·발행·이체 등)
  const controls = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"], [contenteditable="true"], [role="textbox"]')).filter(e => e.offsetParent !== null).length;
  return {
    title: document.title || '',
    url: location.href,
    links, tables, forms, controls,
  };
}
"""


def _page_summary(page) -> dict:
    try:
        s = page.evaluate(_PAGE_SUMMARY_JS)
        if isinstance(s, dict):
            return s
    except Exception as e:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
        log.debug("[explorer] page_summary 실패: %s", e)
    return {"title": "", "url": "", "links": [], "tables": [], "forms": 0}


def _current_url(page) -> str:
    """현재 페이지 URL. 조회 실패 시 빈 문자열."""
    try:
        return page.url or ""
    except Exception:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
        return ""


def _pause_between_pages(delay_s: float, pages_data: list[dict]) -> None:
    """첫 페이지 뒤부터 페이지 이동 사이에 delay_s 초 쉰다(0 이하면 쉬지 않음 = 기존 동작)."""
    if delay_s > 0 and pages_data:
        time.sleep(delay_s)


def _navigate_if_needed(page, url: str, pages_data: list[dict]) -> bool:
    """현재 URL과 다르면 url 로 이동. 이동 실패 시 오류 기록을 pages_data 에 추가하고 False."""
    if _current_url(page) != url:
        try:
            page.goto(url, timeout=20000)
            # 로드 대기 실패해도 계속 진행(안전한 기본값 반환 정책)
            with contextlib.suppress(Exception):
                page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception as e:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
            log.warning("[explorer] goto 실패 %s: %s", url, e)
            pages_data.append({"url": url, "error": f"goto: {str(e)[:120]}"})
            return False
    return True


def _bot_check_page(page, url: str, bot_reports: list[dict]) -> str:
    """봇 레이더 스캔. 봇이 감지되면 중단 사유 문자열, 아니면 빈 문자열."""
    try:
        br = bot_scan(page)
        bot_reports.append({"url": url, "level": br["level"], "vendors": br["vendors"]})
        if br["flagged"]:
            aborted_reason = f"bot_flagged: {br['level']}"
            log.warning("[explorer] 봇 감지 — 중단: %s", aborted_reason)
            return aborted_reason
    except Exception:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
        pass
    return ""


def _form_summary(page, s: dict) -> dict:
    """페이지에 폼이 있으면 자동 탐색 요약을 반환(없거나 실패하면 빈 dict)."""
    form_summary = {}
    if s.get("forms", 0) > 0:
        try:
            disc = discover_form(page)
            form_summary = {
                "intent": disc.intent,
                "roles": sorted({f.role for f in disc.fields if f.score > 0.4}),
                "submit": disc.submit_selector,
            }
        except Exception:  # noqa: BLE001 - 범용 사이트 크롤링 탐색기 - 동일 도메인 검사/URL 이동 실패시 안전한 기본값(False/원본 URL) 반환, 봇 감지시 즉시 중단
            pass
    return form_summary


def _collect_out_links(links: list[dict], url: str, start_url: str, same_host_only: bool) -> list[dict]:
    """페이지 링크를 정규화하고 http(s)/호스트 조건에 맞는 것만 모은다."""
    out_links = []
    for link in links:
        nurl = _norm_url(link.get("href", ""), url)
        if not nurl.startswith(("http://", "https://")):
            continue
        if same_host_only and not _same_host(start_url, nurl):
            continue
        out_links.append({"href": nurl, "text": link.get("text", "")[:80]})
    return out_links


def _save_sitemap(result: dict, host: str) -> None:
    """탐색 결과를 data/sitemap/<host>_auto_<ts>.json 으로 저장하고 result["saved_to"] 기록."""
    SITEMAP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    fp = SITEMAP_DIR / f"{safe_host}_auto_{ts}.json"
    fp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["saved_to"] = str(fp)
    log.info("[explorer] 저장: %s", fp)


def _dedupe_links(out_links: list[dict]) -> list[dict]:
    """href 기준 중복 제거(처음 등장 순서 유지)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for link in out_links:
        if link["href"] in seen:
            continue
        seen.add(link["href"])
        unique.append(link)
    return unique


def _should_skip_url(url: str, start_url: str, host: str, same_host_only: bool, skip_url_patterns: tuple[str, ...]) -> bool:
    """위험 URL(로그아웃/삭제/제출 등) 또는 외부 호스트면 로그를 남기고 True."""
    # 위험 URL 회피
    if any(p in url.lower() for p in skip_url_patterns):
        log.info("[explorer] skip 위험 URL: %s", url)
        return True

    # 같은 호스트
    if same_host_only and host and not _same_host(start_url, url):
        log.debug("[explorer] skip 외부 호스트: %s", url)
        return True
    return False


def _call_on_page(on_page, page) -> None:
    """쪽 직후 콜백(있을 때만). 관측 실패가 탐색을 막지 않는다."""
    if on_page is None:
        return
    try:
        on_page(page)
    except Exception as exc:  # noqa: BLE001 - 관측 실패가 탐색을 막지 않는다
        log.debug("[explorer] on_page 실패: %s", str(exc)[:80])


def explore_site(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    page,
    *,
    depth: int = 2,
    max_pages: int = 20,
    save: bool = True,
    same_host_only: bool = True,
    bot_check_each_page: bool = True,
    skip_url_patterns: tuple[str, ...] = (
        "logout",
        "signout",
        "delete",
        "remove",
        "submit",
    ),
    delay_s: float = 0.0,
    on_page=None,
) -> dict:
    """현재 페이지부터 BFS 탐색.

    Args:
        depth: 최대 깊이
        max_pages: 최대 방문 페이지 수 (budget)
        save: data/sitemap/<host>_auto_<ts>.json 저장 여부
        same_host_only: 같은 호스트만
        bot_check_each_page: 각 페이지에서 봇 레이더 스캔
        skip_url_patterns: 위험 URL 키워드 (로그아웃/삭제/제출 등 자동 회피)
        delay_s: 페이지 이동 사이 대기 초(기본 0 = 기존 동작). 사이트 부담을 줄이려는 호출자가 지정한다.
        on_page: 쪽을 읽은 직후(그 쪽이 열려 있는 동안) `on_page(page)` 를 부른다 — 데이터 소스 관측용. 실패해도 탐색은 계속한다.

    Returns:
        dict{host, started_url, pages, bot_radar, elapsed_s}
    """
    started_at = time.time()
    start_url = _current_url(page)
    host = urlparse(start_url).hostname or ""

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages_data: list[dict] = []
    bot_reports: list[dict] = []
    aborted_reason = ""

    log.info("[explorer] 시작 host=%s start=%s depth=%d max=%d", host, start_url, depth, max_pages)

    while queue and len(pages_data) < max_pages:
        url, d = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        # 위험 URL 회피 / 같은 호스트
        if _should_skip_url(url, start_url, host, same_host_only, skip_url_patterns):
            continue

        # 이동 (현재 URL과 다를 때만)
        _pause_between_pages(delay_s, pages_data)
        if not _navigate_if_needed(page, url, pages_data):
            continue

        # 봇 감지
        if bot_check_each_page:
            aborted_reason = _bot_check_page(page, url, bot_reports)
            if aborted_reason:
                break

        # 페이지 요약
        s = _page_summary(page)
        # 폼 자동 탐색 (있으면)
        form_summary = _form_summary(page, s)

        rec = {
            "url": url,
            "depth": d,
            "title": s.get("title", "")[:120],
            "tables": s.get("tables", [])[:10],
            "forms_count": s.get("forms", 0),
            "controls_count": s.get("controls", 0),
            "form_summary": form_summary,
            "links_out": [],
        }

        # 링크 수집 + 다음 큐
        out_links = _collect_out_links(s.get("links", []), url, start_url, same_host_only)
        queue.extend((out_link["href"], d + 1) for out_link in out_links if out_link["href"] not in visited and d + 1 <= depth)
        # 중복 제거
        rec["links_out"] = _dedupe_links(out_links)[:50]

        pages_data.append(rec)
        _call_on_page(on_page, page)
        log.info(
            "[explorer] [%d/%d] d=%d %s — 링크 %d개",
            len(pages_data),
            max_pages,
            d,
            (s.get("title", "") or url)[:60],
            len(rec["links_out"]),
        )

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
        _save_sitemap(result, host)

    return result
