"""홈페이지부터 사이트 전체 자동 크롤 + 미설계 페이지 자동 반영.

흐름:
  1. 시작 URL (홈/현재 페이지) 에서 출발
  2. BFS 탐색 — 같은 호스트만, 위험 URL 회피, 봇 감지 즉시 중단
  3. 각 페이지마다 classifier 실행 → 타입 분류
  4. 알려진 타입(login/signup/list_table/...) → 권장 핸들러 기록
  5. unknown 타입 → 자동 반영:
       - HTML + 스크린샷 저장
       - 폼/메뉴/버튼/링크 상세 캡처
       - data/discovered/<host>/<page_slug>.json 누적
       - 핸들러 스텁 (TODO 주석) 자동 생성 → suggested_handlers 에 표시
  6. 결과:
       data/sitemap/<host>_crawl_<ts>.json (전체)
       data/discovered/<host>/ (미설계 페이지 자료)

사용:
    python -m scripts.explorer.site_crawler <site> [depth] [max_pages]
    python scripts/cdp_client.py crawl <site> [depth] [max]
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from scripts.explorer.page_classifier import classify_page
from scripts.form.bot_radar import scan as bot_scan
from scripts.logger import get_logger

log = get_logger(__name__)


def _dismiss_popups(page, rounds: int = 3) -> list[dict]:
    """홈페이지/페이지 진입 시 자동 팝업 닫기.

    기존 모듈 재사용:
      - scripts.popup_detector.handle_page_popups: DOM 모달 닫기
      - scripts.popup_detector.close_popup_windows: 별도 창 팝업 닫기
    연쇄 팝업 대비 여러 라운드.
    """
    from scripts.popup_detector import close_popup_windows, handle_page_popups

    all_actions: list[dict] = []
    for i in range(rounds):
        round_actions: list[dict] = []
        # 별도 창 팝업 (window.open)
        try:
            n = close_popup_windows(page)
            if n:
                round_actions.append({"kind": "popup_window", "count": n})
        except Exception as e:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            log.debug("[crawler] close_popup_windows 실패: %s", e)
        # DOM 모달
        try:
            r = handle_page_popups(page, timeout_s=2.0)
            if r and r.get("handled"):
                round_actions.append(
                    {"kind": "dom_modal", "detail": r.get("actions", []) if isinstance(r, dict) else r}
                )
        except Exception as e:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            log.debug("[crawler] handle_page_popups 실패: %s", e)

        if not round_actions:
            break
        all_actions.extend(round_actions)
        log.info("[crawler] 팝업 닫기 라운드 %d: %s", i + 1, round_actions)
    return all_actions


ROOT = Path(__file__).resolve().parents[2]
SITEMAP_DIR = ROOT / "data" / "sitemap"
DISCOVERED_DIR = ROOT / "data" / "discovered"


_SKIP_URL_KEYWORDS = (
    "logout",
    "signout",
    "delete",
    "remove",
    "withdraw",
    "submit",
    "register/save",
    "/upload",
    "/download",
    "javascript:",
    "mailto:",
    "tel:",
)

_BINARY_EXT = (
    ".pdf",
    ".zip",
    ".exe",
    ".docx",
    ".xlsx",
    ".hwp",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".mp4",
    ".avi",
    ".tar",
    ".gz",
)


def _same_host(a: str, b: str) -> bool:
    try:
        ua, ub = urlparse(a), urlparse(b)
        return (ua.hostname or "").lower() == (ub.hostname or "").lower()
    except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return False


def _norm(href: str, base: str) -> str:
    try:
        return urljoin(base, href).split("#")[0]
    except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return href


def _safe_slug(url: str) -> str:
    p = urlparse(url)
    base = (p.path or "/").strip("/") or "root"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", base)[:80]


def _collect_links(page) -> list[dict]:
    """페이지의 a[href] 수집. visibility 너무 엄격하지 않게 — 메뉴 hover/접힘 대응."""
    js = r"""
    () => Array.from(document.querySelectorAll('a[href]')).map(a => {
        const href = a.getAttribute('href') || '';
        return {
            href, text: (a.innerText || '').trim().slice(0, 80),
        };
    }).filter(l => l.href
               && !l.href.startsWith('javascript:')
               && !l.href.startsWith('#')
               && !l.href.startsWith('mailto:')
               && !l.href.startsWith('tel:'));
    """
    try:
        return page.evaluate(js) or []
    except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        return []


def _save_unknown_snapshot(page, host: str, url: str, classify: dict) -> str:
    """미설계 페이지 자동 반영 — DOM/HTML/screenshot/스텁 저장.

    Returns: 저장 경로 (relative)
    """
    slug = _safe_slug(url)
    safe_host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    out_dir = DISCOVERED_DIR / safe_host
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / slug

    # 1) 스크린샷
    try:
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
    except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
        pass
    # 2) HTML
    try:
        html = page.content()
        base.with_suffix(".html").write_text(html, encoding="utf-8")
    except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
        pass
    # 3) 메타 + 핸들러 스텁
    stub = {
        "url": url,
        "captured_at": datetime.now().isoformat(),
        "classify": classify,
        "suggested_handler_stub": _build_handler_stub(url, classify),
    }
    base.with_suffix(".json").write_text(
        json.dumps(stub, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(base.relative_to(ROOT))


def _build_handler_stub(url: str, classify: dict) -> dict:
    """미설계 페이지를 위한 핸들러 코드 스텁 생성 (참고용)."""
    slug = _safe_slug(url)
    snap = classify.get("snapshot", {})
    disc = classify.get("discovery", {})
    code = f'''"""미설계 페이지 핸들러 스텁 — {url}

자동 생성. 필요 시 scripts/<site>/ 패키지로 이관 후 정식 모듈로.
"""
from scripts.form.discovery import discover_form
from scripts.form.human import human_type, human_click


def handle_{slug.replace(".", "_").replace("-", "_")}(page):
    """페이지 타입: {classify.get("type", "?")} (conf={classify.get("confidence")})"""
    # 신호: {classify.get("signals", [])}
    # 권장: {classify.get("suggested_handlers", [])}

    # 1) 필요 시 폼 탐색
    disc = discover_form(page)

    # 2) 검출된 필드: {
        [(f.get("role"), f.get("selector")) for f in disc.get("fields", [])[:5]]
        if isinstance(disc, dict)
        else "(discovery 필요)"
    }

    # TODO: 실제 동작 작성
    raise NotImplementedError("핸들러 구현 필요: {url}")
'''
    return {
        "module_filename": f"handle_{slug}.py",
        "code_skeleton": code,
        "hints": {
            "form_fields_detected": disc.get("fields_count", 0),
            "tables_detected": len(snap.get("tables", [])),
            "modals_detected": len(snap.get("modal_signs", [])),
            "headings": snap.get("headings", [])[:5],
        },
    }


def crawl_site(
    page,
    *,
    start_url: str | None = None,
    depth: int = 3,
    max_pages: int = 50,
    same_host_only: bool = True,
    bot_check_each: bool = True,
    from_homepage_root: bool = True,
    handle_popups: bool = True,
) -> dict:
    """홈페이지부터 BFS 크롤 + 페이지 분류 + 미설계 페이지 반영.

    Args:
        start_url: 명시 시 해당 URL부터. 없으면 현재 페이지 호스트의 루트(/)부터.
        from_homepage_root: True면 현재 호스트의 / 로 강제 이동 (start_url 미지정 시).
        handle_popups: 홈페이지 진입 후 자동 팝업 닫기.
    """
    started_at = time.time()
    initial_popups: list[dict] = []

    # 1) 시작 URL 결정 — 명시 우선, 없으면 현재 호스트 루트
    if start_url:
        seed = start_url
    elif from_homepage_root:
        try:
            cur = page.url or ""
        except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            cur = ""
        cur_host = urlparse(cur).hostname or ""
        if cur_host:
            seed = f"{urlparse(cur).scheme or 'https'}://{cur_host}/"
        else:
            seed = cur
    else:
        try:
            seed = page.url or ""
        except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            seed = ""

    # 2) 시작 URL 로 이동
    if seed:
        log.info("[crawler] 시작 URL 진입: %s", seed)
        try:
            page.goto(seed, timeout=20000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
                pass
        except Exception as e:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            log.warning("[crawler] 시작 URL goto 실패: %s", e)

    # 3) 홈페이지 팝업 자동 처리 (연쇄 팝업 포함)
    if handle_popups:
        initial_popups = _dismiss_popups(page, rounds=3)
        if initial_popups:
            log.info("[crawler] 홈페이지 팝업 %d라운드 처리", len(initial_popups))

    # 4) seed 갱신 (팝업 닫고 나서 redirect 있을 수 있음)
    try:
        seed_url = page.url
    except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
        seed_url = seed
    host = urlparse(seed_url).hostname or ""

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(seed_url, 0)]
    pages: list[dict] = []
    discovered_paths: list[str] = []
    aborted = ""
    type_counts: dict[str, int] = {}

    log.info("[crawler] start host=%s seed=%s depth=%d max=%d", host, seed_url, depth, max_pages)

    while queue and len(pages) < max_pages:
        url, d = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        # 회피 패턴
        low = url.lower()
        if any(k in low for k in _SKIP_URL_KEYWORDS):
            continue
        if low.endswith(_BINARY_EXT):
            continue
        if same_host_only and host and not _same_host(seed_url, url):
            continue

        # 이동
        try:
            cur = page.url or ""
        except Exception:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
            cur = ""
        if cur != url:
            try:
                page.goto(url, timeout=20000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
                    pass
            except Exception as e:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
                log.warning("[crawler] goto 실패 %s: %s", url, e)
                pages.append({"url": url, "error": f"goto: {str(e)[:120]}"})
                continue

        # 이동 직후 팝업 자동 닫기 (1라운드만 — BFS 속도 유지)
        if handle_popups:
            try:
                _dismiss_popups(page, rounds=1)
            except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
                pass

        # 봇 감지
        if bot_check_each:
            try:
                br = bot_scan(page)
                if br.get("flagged"):
                    aborted = f"bot_flagged: {br['level']}"
                    log.warning("[crawler] 봇 감지 중단: %s", aborted)
                    break
            except Exception:  # noqa: BLE001 - 팝업 닫기/스냅샷 저장 등 보조 동작 — 실패해도 크롤링 계속 진행 가능(2026-09-28 검토)
                pass

        # 분류
        info = classify_page(page)
        page_type = info["type"]
        type_counts[page_type] = type_counts.get(page_type, 0) + 1

        rec = {
            "url": url,
            "depth": d,
            "title": (info["snapshot"].get("title") or "")[:120],
            "type": page_type,
            "confidence": info["confidence"],
            "signals": info["signals"],
            "suggested_handlers": info["suggested_handlers"],
            "form_intent": info["discovery"].get("intent"),
        }

        # 미설계 → 자동 반영
        if page_type == "unknown":
            try:
                saved = _save_unknown_snapshot(page, host, url, info)
                rec["discovered_to"] = saved
                discovered_paths.append(saved)
                log.info("[crawler] [미설계 반영] %s → %s", url, saved)
            except Exception as e:  # noqa: BLE001 - 사이트 탐색 크롤러 — 읽기 전용 페이지 순회/스냅샷 저장, 실패는 로그 후 안전한 기본값(빈 문자열/빈 리스트)으로 폴백, 쓰기·결제 없음(2026-09-28 검토)
                log.warning("[crawler] snapshot 저장 실패 %s: %s", url, e)

        pages.append(rec)
        log.info("[crawler] [%d/%d] d=%d %s (%s)", len(pages), max_pages, d, (rec["title"] or url)[:60], page_type)

        # 링크 수집 + 큐 추가
        if d + 1 <= depth:
            for link in _collect_links(page):
                nurl = _norm(link.get("href", ""), url)
                if not nurl.startswith(("http://", "https://")):
                    continue
                if same_host_only and not _same_host(seed_url, nurl):
                    continue
                if nurl not in visited:
                    queue.append((nurl, d + 1))

    elapsed = round(time.time() - started_at, 2)
    result = {
        "host": host,
        "seed_url": seed_url,
        "depth": depth,
        "max_pages": max_pages,
        "visited_count": len(pages),
        "elapsed_s": elapsed,
        "aborted_reason": aborted,
        "type_counts": type_counts,
        "discovered_count": len(discovered_paths),
        "discovered_paths": discovered_paths,
        "homepage_popups_handled": initial_popups,
        "pages": pages,
    }

    # 사이트맵 저장
    if host:
        SITEMAP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_host = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
        fp = SITEMAP_DIR / f"{safe_host}_crawl_{ts}.json"
        fp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["saved_to"] = str(fp.relative_to(ROOT))
        log.info("[crawler] saved %s (방문 %d, 미설계 %d)", fp, len(pages), len(discovered_paths))

    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.explorer.site_crawler <site> [depth] [max_pages]")
        return
    site = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    max_pages = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    from scripts.site_access import open_site

    page = open_site(site)
    result = crawl_site(page, depth=depth, max_pages=max_pages)
    print("\n✓ 크롤 완료")
    print(f"  방문: {result['visited_count']} / 미설계 반영: {result['discovered_count']}")
    print(f"  타입 분포: {result['type_counts']}")
    if result.get("saved_to"):
        print(f"  사이트맵: {result['saved_to']}")
    if result.get("aborted_reason"):
        print(f"  중단: {result['aborted_reason']}")


if __name__ == "__main__":
    main()
