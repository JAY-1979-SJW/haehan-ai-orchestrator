"""네이버 쇼핑 경쟁사 조사 CLI 도구.

사용법:
    python scripts/naver/shopping/cli.py search "LED 무드등"
    python scripts/naver/shopping/cli.py search "인테리어 조명" --display 20
    python scripts/naver/shopping/cli.py history "LED 무드등"
    python scripts/naver/shopping/cli.py summary
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
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
        print(f"\n  상위 상품:")
        for item in r["items"][:10]:
            title = (item.get("title") or "")[:45]
            price = _fmt(item.get("lprice"))
            mall  = item.get("mall_name", "-")
            brand = item.get("brand") or "-"
            print(f"    {title:<45} | {price:>8}원 | {mall} | {brand}")


def cmd_summary(args):
    from ai_orchestrator.connectors import naver_search_queries as q
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
            lo, avg, hi = min(prices), sum(prices)//len(prices), max(prices)
        else:
            lo = avg = hi = None
        print(f"  {kw:<23} {d['count']:>5} {_fmt(lo):>9} {_fmt(avg):>9} {_fmt(hi):>9}")


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

    args = parser.parse_args()
    {"search": cmd_search, "history": cmd_history, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    main()
