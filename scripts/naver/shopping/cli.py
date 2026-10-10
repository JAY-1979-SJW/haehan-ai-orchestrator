"""네이버 쇼핑 경쟁사 조사 CLI 도구.

사용법:
    # OpenAPI (비로그인, 가격/브랜드/카테고리)
    python scripts/naver/shopping/cli.py search "LED 무드등"
    python scripts/naver/shopping/cli.py search "인테리어 조명" --display 40
    python scripts/naver/shopping/cli.py history "LED 무드등"
    python scripts/naver/shopping/cli.py summary

    # CDP 크롤링 (리뷰·별점·순위 포함)
    python scripts/naver/shopping/cli.py crawl "LED 무드등"
    python scripts/naver/shopping/cli.py crawl "인테리어 조명" --limit 40
    python scripts/naver/shopping/cli.py crawl-report "LED 무드등"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # repo root (2026-08-14: [4]는 저장소 밖 C:\work 를 가리켰음)
sys.path.insert(0, str(ROOT))

# .env 로드
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n or "-")


def cmd_search(args):
    from scripts.naver.shopping import search_shopping

    print(f"\n🔍 쇼핑 검색: {args.query} (display={args.display})")
    result = search_shopping(args.query, display=args.display)
    print(f"  status   : {result['status']}")
    print(f"  수집 건수: {result['item_count']}")
    print(f"  DB 상태  : {result['db_status']}")
    print(f"  삽입 건수: {result.get('inserted', 0)}")
    print(f"  일일 한도: {result['daily_limit']:,} 회")


def cmd_history(args):
    from scripts.naver.shopping import price_summary

    print(f"\n📊 가격 통계: {args.query}")
    r = price_summary(args.query)
    if not r.get("count"):
        print("  수집 데이터 없음 — 먼저 search 실행")
        return
    print(f"  수집 건수: {r['count']}")
    print(f"  최저가  : {_fmt(r['min_price'])}원")
    print(f"  평균가  : {_fmt(r['avg_price'])}원")
    print(f"  최고가  : {_fmt(r['max_price'])}원")
    if r.get("items"):
        print("\n  상위 상품:")
        for item in r["items"][:10]:
            title = (item.get("title") or "")[:45]
            price = _fmt(item.get("lprice"))
            mall = item.get("mall_name", "-")
            brand = item.get("brand") or "-"
            print(f"    {title:<45} | {price:>8}원 | {mall} | {brand}")


def cmd_summary(args):
    from scripts.naver.shopping import naver_search_queries as q

    page = q.search_shopping_items(limit=200, offset=0)
    if not page.total:
        print("수집 데이터 없음")
        return

    # 키워드별 집계
    stats: dict = {}
    for item in page.items:
        kw = item.get("query", "unknown")
        price = item.get("lprice")
        if kw not in stats:
            stats[kw] = {"count": 0, "prices": []}
        stats[kw]["count"] += 1
        if price:
            stats[kw]["prices"].append(price)

    print(f"\n📦 쇼핑 DB 전체 요약 (총 {page.total}건)")
    print(f"{'키워드':<25} {'건수':>5} {'최저':>9} {'평균':>9} {'최고':>9}")
    print("-" * 65)
    for kw, d in sorted(stats.items()):
        prices = d["prices"]
        if prices:
            lo, avg, hi = min(prices), sum(prices) // len(prices), max(prices)
        else:
            lo = avg = hi = None
        print(f"  {kw:<23} {d['count']:>5} {_fmt(lo):>9} {_fmt(avg):>9} {_fmt(hi):>9}")


def cmd_crawl(args):
    from scripts.naver.shopping.crawl import crawl_shopping
    from scripts.naver.shopping.gate import gate_competitor

    gate_competitor(args.query)
    print(f"\n🕷️  CDP 크롤링: {args.query} (최대 {args.limit}개)")
    print("  브라우저 탐색 중...", end="", flush=True)
    r = crawl_shopping(args.query, limit=args.limit)
    if not r.get("ok"):
        print(f"\n❌ 오류: {r.get('error')}")
        return
    print(f"\n✅ 수집 완료: {r['count']}개\n")
    s = r["stats"]
    print(
        f"  가격   최저 {_fmt(s['price'].get('min'))}원 / 평균 {_fmt(s['price'].get('avg'))}원 / 최고 {_fmt(s['price'].get('max'))}원"
    )
    print(
        f"  리뷰   최소 {_fmt(s['review'].get('min'))} / 평균 {_fmt(s['review'].get('avg'))} / 최대 {_fmt(s['review'].get('max'))} / 합계 {_fmt(s['review'].get('total'))}"
    )
    print(f"  별점   평균 {s['rating'].get('avg') or '-'} / 최고 {s['rating'].get('max') or '-'}")
    print(f"\n  {'순위':>3} {'상품명':<40} {'가격':>9} {'리뷰':>6} {'별점':>5} {'판매몰'}")
    print("  " + "-" * 85)
    for p in r["products"][: args.limit]:
        print(
            f"  {p.get('rank', ''):>3} {(p.get('title') or '')[:40]:<40} "
            f"{_fmt(p.get('price')):>9}원 "
            f"{_fmt(p.get('review_count')):>6} "
            f"{p.get('rating') or '-'!s:>5} "
            f"{p.get('mall') or '-'}"
        )


def cmd_crawl_report(args):
    from scripts.naver.shopping.crawl import full_summary
    from scripts.naver.shopping.gate import gate_competitor

    gate_competitor(args.query)
    print(f"\n📋 크롤링 보고서: {args.query}")
    r = full_summary(args.query)
    if not r.get("count"):
        print("  수집 데이터 없음 — crawl 먼저 실행")
        return
    print(f"  수집: {r['count']}건")
    if r.get("price"):
        print(
            f"  가격: 최저 {_fmt(r['price']['min'])}원 / 평균 {_fmt(r['price']['avg'])}원 / 최고 {_fmt(r['price']['max'])}원"
        )
    if r.get("review"):
        print(
            f"  리뷰: 평균 {_fmt(r['review']['avg'])} / 최대 {_fmt(r['review']['max'])} / 총 {_fmt(r['review']['total'])}"
        )
    if r.get("rating"):
        print(f"  별점: 평균 {r['rating']['avg']} / 최고 {r['rating']['max']}")
    print(f"\n  {'순위':>3} {'상품명':<40} {'가격':>9} {'리뷰':>7} {'별점':>5} {'판매몰'}")
    print("  " + "-" * 85)
    for p in r.get("top10", []):
        print(
            f"  {p.get('rank', ''):>3} {(p.get('title') or '')[:40]:<40} "
            f"{_fmt(p.get('price')):>9}원 "
            f"{_fmt(p.get('review_count')):>7} "
            f"{p.get('rating') or '-'!s:>5} "
            f"{p.get('mall') or '-'}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="네이버 쇼핑 경쟁사 조사 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="쇼핑 검색 수집")
    p_search.add_argument("query", help="검색어 (예: LED 무드등)")
    p_search.add_argument("--display", type=int, default=10, help="수집 건수 (기본 10)")

    p_hist = sub.add_parser("history", help="가격 통계 조회")
    p_hist.add_argument("query", help="검색어")

    sub.add_parser("summary", help="전체 DB 요약")

    p_crawl = sub.add_parser("crawl", help="CDP 브라우저 크롤링 (리뷰·별점 포함)")
    p_crawl.add_argument("query", help="검색어")
    p_crawl.add_argument("--limit", type=int, default=40, help="수집 건수 (기본 40)")

    p_report = sub.add_parser("crawl-report", help="크롤링 결과 보고서")
    p_report.add_argument("query", help="검색어")

    args = parser.parse_args()
    {
        "search": cmd_search,
        "history": cmd_history,
        "summary": cmd_summary,
        "crawl": cmd_crawl,
        "crawl-report": cmd_crawl_report,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
