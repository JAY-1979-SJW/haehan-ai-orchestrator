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

sys.path.insert(0, ".")

from scripts.logger import get_logger
from scripts.naver.blog.management.analytics import BlogAnalytics

_log = get_logger(__name__)


def run(blog_id: str = "skyjwsin") -> dict:
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://localhost:9222")
    page = browser.contexts[0].pages[0]

    ba = BlogAnalytics(page, blog_id)
    report = ba.full_report()

    browser.close()
    pw.stop()

    _print_summary(report)
    return report


def _print_summary(report: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f"  블로그 분석 — {report['blog_id']}  ({report['generated_at']})")
    print(f"{'=' * 60}\n")

    today = report.get("today", {})
    print(f"[오늘] 방문 {today.get('visitors_today', '-')}  |  누적 {today.get('visitors_total', '-')}\n")

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

    rank = report.get("rank_pv", {})
    if rank.get("ok"):
        print(f"[글별 조회수 순위 — {rank.get('period')}]")
        for p in rank.get("posts", [])[:10]:
            print(f"  {p['rank']:>2}. ({p['pv']:>3}회) {p['title'][:45]}")
        print()

    trend = report.get("visit_trend", {})
    if trend.get("ok"):
        print(f"[방문 추이 — 최근 {len(trend.get('trend', []))}일]")
        for t in trend.get("trend", [])[:14]:
            print(f"  {t['date']}  {t['total']:>4}")
        print()

    device = report.get("device", {})
    if device.get("ok") and device.get("device"):
        d = device["device"]
        print(f"[기기별] 모바일 {d.get('mobile', '-')}%  |  PC {d.get('pc', '-')}%\n")

    demo = report.get("demo", {})
    if demo.get("ok"):
        rows = [r for r in demo.get("breakdown", []) if r["age"] != "전체" and r["count"] > 0]
        if rows:
            print("[성별·연령별 분포]")
            for r in sorted(rows, key=lambda r: -r["count"]):
                print(f"  {r['age']:<6} {r['gender']}  {r['count']:>3}건 ({r['pct']:.1f}%)")
            print()

    print(f"저장: {report.get('_file')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog-id", default="skyjwsin")
    args = parser.parse_args()
    run(blog_id=args.blog_id)
