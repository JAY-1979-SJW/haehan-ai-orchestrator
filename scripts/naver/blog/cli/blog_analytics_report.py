"""네이버 블로그(skyjwsin) 상세 분석 리포트 — CDP로 admin.blog.naver.com/stat/* 조회.

실제 로직은 scripts/naver/blog/management/analytics.py::BlogAnalytics 에 있다
(기존 방문자 시계열 수집기에 유입경로/글별 조회수 순위/방문 추이 스크래핑을
추가한 것 — 신규 모듈 아님).

실행:
  python scripts/naver/blog/cli/blog_analytics_report.py [--blog-id skyjwsin]

출력: data/reports/blog_analytics_{blog_id}_{날짜}.json 저장 + 콘솔 요약.
"""

from __future__ import annotations

import argparse
import sys

from scripts.naver.blog.accounts import BLOG_ACCOUNTS, DEFAULT_ACCOUNT

sys.path.insert(0, ".")

from scripts.common.logger import get_logger
from scripts.naver.blog.management.analytics import BlogAnalytics

_log = get_logger(__name__)


def run(blog_id: str = DEFAULT_ACCOUNT, ensure_login: bool = False) -> dict:
    """blog_id 리포트 1건. ensure_login=True면 다른 계정이 로그인돼 있어도
    이 계정으로 전환한 뒤 조회한다(--compare에서 계정을 오갈 때 필요)."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    page = browser.contexts[0].pages[0]

    if ensure_login:
        from scripts.naver.blog.marketing.publish import connect_and_ensure_login

        pw.stop()
        pw, browser, page = connect_and_ensure_login(blog_id=blog_id)
        if page is None:
            pw.stop()
            raise RuntimeError(f"{blog_id} 로그인 실패 — 브라우저에서 직접 로그인 후 재시도하세요")

    ba = BlogAnalytics(page, blog_id)
    report = ba.full_report()

    browser.close()
    pw.stop()

    _print_summary(report)
    return report


def run_compare(blog_ids: list[str]) -> dict:
    """계정별 리포트를 순서대로 조회해 나란히 비교한다.

    같은 CDP 세션을 계정만 바꿔가며 재사용한다 — 계정마다 프로필을 새로
    띄우지 않는다(로그인 세션 보존 원칙, CLAUDE.md).
    """
    reports = {}
    for i, bid in enumerate(blog_ids):
        reports[bid] = run(blog_id=bid, ensure_login=(i > 0))  # 첫 계정은 이미 로그인돼 있다고 가정

    print(f"\n{'=' * 60}")
    print("  계정별 비교")
    print(f"{'=' * 60}")
    print(f"{'계정':<12} {'오늘 방문':>10} {'누적 방문':>10} {'PV 상위 1위':>14}")
    for bid, r in reports.items():
        today = r.get("today", {})
        top = (r.get("rank_pv", {}).get("posts") or [{}])[0]
        print(
            f"{bid:<12} {today.get('visitors_today', '-')!s:>10} "
            f"{today.get('visitors_total', '-')!s:>10} {top.get('pv', '-')!s:>14}"
        )
    return reports


def _print_referer(report: dict) -> None:
    """유입경로 출력."""
    referer = report.get("referer", {})
    if referer.get("ok"):
        print("[유입경로]")
        for s in referer.get("sources", []):
            print(f"  {s['path']:<20} {s['pct']:>5.2f}%")
        if referer.get("search_terms"):
            print("  검색어:")
            for t in referer["search_terms"][:5]:
                print(f"    {t['term']:<20} {t['pct']:>5.2f}%")
        print()


def _print_rank(report: dict) -> None:
    """글별 조회수 순위 출력."""
    rank = report.get("rank_pv", {})
    if rank.get("ok"):
        print(f"[글별 조회수 순위 — {rank.get('period')}]")
        for p in rank.get("posts", [])[:10]:
            print(f"  {p['rank']:>2}. ({p['pv']:>3}회) {p['title'][:45]}")
        print()


def _print_trend(report: dict) -> None:
    """방문 추이 출력."""
    trend = report.get("visit_trend", {})
    if trend.get("ok"):
        print(f"[방문 추이 — 최근 {len(trend.get('trend', []))}일]")
        for t in trend.get("trend", [])[:14]:
            print(f"  {t['date']}  {t['total']:>4}")
        print()


def _print_device(report: dict) -> None:
    """기기별 출력."""
    device = report.get("device", {})
    if device.get("ok") and device.get("device"):
        d = device["device"]
        print(f"[기기별] 모바일 {d.get('mobile', '-')}%  |  PC {d.get('pc', '-')}%\n")


def _print_demo(report: dict) -> None:
    """성별·연령별 분포 출력."""
    demo = report.get("demo", {})
    if demo.get("ok"):
        rows = [r for r in demo.get("breakdown", []) if r["age"] != "전체" and r["count"] > 0]
        if rows:
            print("[성별·연령별 분포]")
            for r in sorted(rows, key=lambda r: -r["count"]):
                print(f"  {r['age']:<6} {r['gender']}  {r['count']:>3}건 ({r['pct']:.1f}%)")
            print()


def _print_summary(report: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  블로그 분석 — {report['blog_id']}  ({report['generated_at']})")
    print(f"{'=' * 60}\n")

    today = report.get("today", {})
    print(f"[오늘] 방문 {today.get('visitors_today', '-')}  |  누적 {today.get('visitors_total', '-')}\n")

    _print_referer(report)

    _print_rank(report)

    _print_trend(report)

    _print_device(report)

    _print_demo(report)

    print(f"저장: {report.get('_file')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog-id", default=DEFAULT_ACCOUNT)
    parser.add_argument("--compare", action="store_true", help="skyjwsin·skyjwshin 두 계정을 순서대로 조회해 비교")
    args = parser.parse_args()
    if args.compare:
        run_compare(list(BLOG_ACCOUNTS))
    else:
        run(blog_id=args.blog_id)
