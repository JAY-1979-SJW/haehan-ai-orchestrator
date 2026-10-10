"""등재된 모든 사이트 자동 순회 + 사이트맵 추출 + 통합 보고서.

동작:
  1. page_helper._CRITICAL_SITE_PATTERNS에 등재된 모든 사이트 URL 추출
  2. 각 사이트의 메인 페이지 순회
  3. 페이지마다 자동으로 추출:
     - 페이지 제목 / 메뉴 구조 / 폼 입력 / 다운로드 링크 / 로그인 필요 여부
  4. data/sitemap/{도메인}_auto.json 으로 저장
  5. 통합 보고서: data/site_explorer_report_{YYYYMMDD}.md

사용:
  python scripts/site_explorer.py                 # 전체 등재 사이트 순회
  python scripts/site_explorer.py --category BANK_VISIT   # 카테고리 한정
  python scripts/site_explorer.py --limit 10      # 처음 N개만
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import (  # noqa: E402 - 레거시 sys.path 조작 후 import
    get_page,
)
from scripts.browser.page.page_helper_common import (  # noqa: E402 - 레거시 sys.path 조작 후 import
    _CRITICAL_SITE_PATTERNS,
    is_work_category,
)
from scripts.browser.popup.popup_detector import (  # noqa: E402 - 레거시 sys.path 조작 후 import
    handle_page_popups,
)
from scripts.common.critical_logger import (  # noqa: E402 - 레거시 sys.path 조작 후 import
    log_critical,
)
from scripts.common.logger import (  # noqa: E402 - 레거시 sys.path 조작 후 import
    get_logger,
)

_log = get_logger(__name__)
TODAY = date.today()

SITEMAP_DIR = ROOT / "data" / "sitemap"
SITEMAP_DIR.mkdir(parents=True, exist_ok=True)


# ── 사이트 URL 카탈로그 빌드 ────────────────────────────────────────────────


def build_catalog() -> list[dict]:
    """등재된 모든 사이트를 (category, domain, url) 리스트로 변환"""
    catalog = []
    for category, domains in _CRITICAL_SITE_PATTERNS.items():
        for d in domains:
            # 도메인만 등재된 경우 https:// 자동 prefix
            if d.startswith("http"):
                url = d
            elif "/" in d:
                url = f"https://{d}"
            else:
                url = f"https://www.{d}" if not d.startswith("www.") else f"https://{d}"
            catalog.append({"category": category, "domain": d, "url": url})
    return catalog


# ── 페이지 메타데이터 추출 ──────────────────────────────────────────────────

EXTRACT_JS = r"""
(() => {
    const isVisible = (el) => {
        const s = window.getComputedStyle(el);
        if (s.display === 'none' || s.visibility === 'hidden') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 || rect.height > 0;
    };

    // 1. 페이지 기본 정보
    const result = {
        title: document.title || '',
        url: location.href,
        lang: document.documentElement.lang || '',
        charset: document.characterSet || '',
        meta_description: document.querySelector('meta[name="description"]')?.content || '',
    };

    // 2. 로그인 필요 여부 추정
    const txt = (document.body?.innerText || '').toLowerCase();
    const loginKw = ['로그인', 'login', 'sign in', '본인인증', '인증서', 'pw', 'id'];
    const hasLoginText = loginKw.some(k => txt.includes(k.toLowerCase()));
    const hasPwField = !!document.querySelector('input[type="password"]');
    result.login_required = hasPwField || hasLoginText;

    // 3. 메뉴 항목 (네비게이션)
    const menus = [];
    const seenMenu = new Set();
    document.querySelectorAll('nav a, [role=navigation] a, .gnb a, .lnb a, .menu a, header a').forEach(a => {
        const t = (a.innerText || '').trim().replace(/\s+/g, ' ').substring(0, 30);
        const h = a.href || '';
        if (t && t.length < 30 && t.length >= 2 && !seenMenu.has(t)) {
            seenMenu.add(t);
            menus.push({text: t, href: h.substring(0, 120)});
        }
    });
    result.menus = menus.slice(0, 30);

    // 4. 폼 (입력 화면 후보)
    const forms = [];
    document.querySelectorAll('form').forEach(f => {
        const inputs = Array.from(f.querySelectorAll('input, select, textarea')).map(i => ({
            type: i.type || i.tagName,
            name: i.name || i.id || '',
            placeholder: i.placeholder || ''
        })).filter(i => i.type !== 'hidden').slice(0, 10);
        if (inputs.length) {
            forms.push({
                action: (f.action || '').substring(0, 120),
                method: f.method || '',
                inputs: inputs
            });
        }
    });
    result.forms = forms.slice(0, 5);

    // 5. 다운로드/파일 링크
    const downloads = [];
    document.querySelectorAll('a').forEach(a => {
        const h = a.href || '';
        const t = (a.innerText || '').trim();
        if (/\.(pdf|xlsx?|hwp|zip|exe|csv|docx?)(\?|$)/i.test(h) ||
            /다운로드|download/i.test(t)) {
            downloads.push({text: t.substring(0, 30), href: h.substring(0, 120)});
        }
    });
    result.downloads = downloads.slice(0, 10);

    // 6. 보안 모듈 키워드 탐지
    const secuKw = ['AnySign', 'TouchEn', 'Veraport', 'INISAFE', 'XecureWeb',
                    'WizIN', 'NPKI', 'CrossEx', 'IPinside', '전자금융사기예방'];
    result.security_modules = secuKw.filter(k => (document.body?.innerHTML || '').includes(k));

    // 7. 외부 도메인 카운트
    const externalDomains = {};
    document.querySelectorAll('a[href^=http]').forEach(a => {
        try {
            const u = new URL(a.href);
            if (u.hostname !== location.hostname) {
                externalDomains[u.hostname] = (externalDomains[u.hostname] || 0) + 1;
            }
        } catch(e) {}
    });
    result.external_domains = Object.entries(externalDomains)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([d, c]) => ({domain: d, count: c}));

    // 8. 통계
    result.stats = {
        link_count: document.querySelectorAll('a').length,
        form_count: document.querySelectorAll('form').length,
        input_count: document.querySelectorAll('input, select, textarea').length,
        button_count: document.querySelectorAll('button').length,
        iframe_count: document.querySelectorAll('iframe').length,
    };

    return result;
})();
"""


def extract_page_meta(page) -> dict:
    return page.evaluate(EXTRACT_JS)


# ── 사이트 1개 탐색 ──────────────────────────────────────────────────────────


def explore_site(page, site: dict, timeout_s: int = 15) -> dict:
    """사이트 1개 메인 페이지 탐색"""
    url = site["url"]
    domain = urlparse(url).hostname or site["domain"]
    result = {
        "category": site["category"],
        "domain": domain,
        "url": url,
        "explored_at": datetime.now().isoformat(timespec="seconds"),
        "success": False,
        "error": None,
        "meta": {},
    }

    try:
        # 업무 카테고리만 감사 로그 기록 (업무 외는 사이트맵만 수집)
        if is_work_category(site["category"]):
            log_critical(site["category"], f"사이트 자동 탐색 시작: {domain}", url=url, mode="explorer")
        page.goto(url, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        time.sleep(2)
        # 팝업 닫기 시도 실패는 탐색에 영향 없어 무시하고 계속 진행 — 읽기전용 탐색
        with contextlib.suppress(Exception):
            handle_page_popups(page, timeout_s=2.0)
        meta = extract_page_meta(page)
        result["meta"] = meta
        result["success"] = True

        # 사이트맵 저장
        out = SITEMAP_DIR / f"{domain}_auto.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:  # noqa: BLE001 - 사이트 구조 탐색 스크립트(읽기전용) — 팝업닫기 실패는 무시(pass)하고 계속 탐색, 탐색 자체 실패는 결과 dict에 오류 기록 후 반환할 뿐 쓰기 동작 없음
        result["error"] = str(e)[:200]
        _log.warning("[%s] 탐색 실패: %s", domain, e)

    return result


# ── 보고서 생성 ──────────────────────────────────────────────────────────────


def build_report(results: list[dict]) -> str:
    by_cat: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    lines = []
    lines.append("# 등재 사이트 자동 탐색 보고서")
    lines.append("")
    lines.append(f"- 기준일: {TODAY}")
    lines.append(f"- 전체 사이트: {len(results)}개")
    lines.append(f"- 성공: {sum(1 for r in results if r['success'])}개")
    lines.append(f"- 실패: {sum(1 for r in results if not r['success'])}개")
    lines.append(f"- 카테고리: {len(by_cat)}개")
    lines.append("")

    lines.append("## 카테고리별 요약")
    lines.append("")
    lines.append("| 카테고리 | 사이트수 | 성공 | 실패 | 로그인 필요 | 보안모듈 사용 |")
    lines.append("|---------|---------|------|------|------------|-------------|")
    for cat in sorted(by_cat):
        items = by_cat[cat]
        ok = sum(1 for r in items if r["success"])
        fail = len(items) - ok
        login_n = sum(1 for r in items if r["success"] and r["meta"].get("login_required"))
        secu_n = sum(1 for r in items if r["success"] and r["meta"].get("security_modules"))
        lines.append(f"| {cat} | {len(items)} | {ok} | {fail} | {login_n} | {secu_n} |")
    lines.append("")

    lines.append("## 사이트별 상세")
    lines.append("")
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for r in by_cat[cat]:
            domain = r["domain"]
            if not r["success"]:
                lines.append(f"- ❌ **{domain}** — {r['error']}")
                continue
            m = r["meta"]
            login_mark = " 🔐" if m.get("login_required") else ""
            secu = ", ".join(m.get("security_modules") or [])
            secu_mark = f" 🛡 {secu}" if secu else ""
            lines.append(f"- ✓ **{domain}**{login_mark}{secu_mark}")
            lines.append(f"  - 제목: {m.get('title', '')[:60]}")
            stats = m.get("stats", {})
            lines.append(
                f"  - 통계: 링크 {stats.get('link_count', 0)} / 폼 {stats.get('form_count', 0)} / 입력 {stats.get('input_count', 0)} / iframe {stats.get('iframe_count', 0)}"
            )
            menus = m.get("menus") or []
            if menus:
                menu_str = ", ".join(mm["text"] for mm in menus[:8])
                lines.append(f"  - 메뉴: {menu_str}")
            dls = m.get("downloads") or []
            if dls:
                lines.append(f"  - 다운로드 링크 {len(dls)}개")
        lines.append("")

    return "\n".join(lines)


# ── 메인 ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="등재 사이트 자동 순회 + 사이트맵 수집")
    parser.add_argument("--category", default=None, help="특정 카테고리만 (예: BANK_VISIT)")
    parser.add_argument("--limit", type=int, default=0, help="처음 N개만 (0=전체)")
    parser.add_argument("--timeout", type=int, default=15, help="사이트당 타임아웃(초)")
    parser.add_argument("--skip-failed", action="store_true", help="실패 사이트 보고서 제외")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="data/sitemap/{도메인}_auto.json 이미 있으면 건너뜀 (신규 추가분만 처리)",
    )
    args = parser.parse_args()

    catalog = build_catalog()
    if args.category:
        catalog = [s for s in catalog if s["category"] == args.category]

    # --skip-existing: 사이트맵 이미 있으면 제외
    if args.skip_existing:
        before = len(catalog)
        filtered = []
        for s in catalog:
            domain = urlparse(s["url"]).hostname or s["domain"]
            if (SITEMAP_DIR / f"{domain}_auto.json").exists():
                continue
            filtered.append(s)
        catalog = filtered
        print(f"  [skip-existing] {before}개 중 {len(catalog)}개만 신규 처리")

    if args.limit > 0:
        catalog = catalog[: args.limit]

    print(f"\n{'=' * 70}")
    print("  등재 사이트 자동 탐색")
    print(f"  대상: {len(catalog)}개  |  카테고리: {args.category or '전체'}  |  타임아웃: {args.timeout}초")
    print(f"{'=' * 70}\n")

    page = get_page()
    results = []
    for i, site in enumerate(catalog, 1):
        domain = urlparse(site["url"]).hostname or site["domain"]
        print(f"  [{i:3}/{len(catalog)}] [{site['category']:<18}] {domain}", end=" ", flush=True)
        r = explore_site(page, site, timeout_s=args.timeout)
        results.append(r)
        if r["success"]:
            m = r.get("meta") or {}
            login = "🔐" if m.get("login_required") else "·"
            secu = "🛡" if m.get("security_modules") else "·"
            print(f"✓  {login}{secu}  {(m.get('title') or '')[:40]}")
        else:
            err = r.get("error") or "unknown"
            print(f"✗  {err[:50]}")
        time.sleep(0.5)

    # 보고서
    report = build_report(results)
    rpt_path = ROOT / "data" / f"site_explorer_report_{TODAY.strftime('%Y%m%d')}.md"
    rpt_path.write_text(report, encoding="utf-8")

    # JSON 통합 결과
    json_path = ROOT / "data" / f"site_explorer_result_{TODAY.strftime('%Y%m%d')}.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 70}")
    print(f"  완료 | 성공 {sum(1 for r in results if r['success'])}/{len(results)}")
    print(f"  보고서: {rpt_path.name}")
    print(f"  JSON:   {json_path.name}")
    print(f"  사이트맵: data/sitemap/*_auto.json ({len([r for r in results if r['success']])}개)")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자 중단")
        sys.exit(0)
    except Exception as e:  # noqa: BLE001 - 사이트 구조 탐색 스크립트(읽기전용) — 팝업닫기 실패는 무시(pass)하고 계속 탐색, 탐색 자체 실패는 결과 dict에 오류 기록 후 반환할 뿐 쓰기 동작 없음
        _log.error("실행 실패: %s", e)
        import traceback

        traceback.print_exc()
        sys.exit(1)
