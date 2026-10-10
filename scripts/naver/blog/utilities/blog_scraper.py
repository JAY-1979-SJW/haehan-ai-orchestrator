"""네이버 블로그 대량 수집 스크립트.

사용법:
    # 단일 블로그 수집
    python scripts/naver/blog/blog_scraper.py \
        --blog https://blog.naver.com/skyjwshin --pages 3

    # 본문+댓글+이미지 포함
    python scripts/naver/blog/blog_scraper.py \
        --blog https://blog.naver.com/skyjwshin --pages 5 --full --images

    # 여러 블로그 수집
    python scripts/naver/blog/blog_scraper.py \
        --blogs "https://blog.naver.com/blog1,https://blog.naver.com/blog2" --max 20

    # 키워드 모니터링
    python scripts/naver/blog/blog_scraper.py \
        --keywords "파이썬,개발" --pages 3 --full

    # 검색 결과 수집
    python scripts/naver/blog/blog_scraper.py \
        --search "머신러닝" --pages 5 --full

    # 블로거 추적
    python scripts/naver/blog/blog_scraper.py \
        --track https://blog.naver.com/skyjwshin --out tracking/snapshot.json

    # CSV 저장
    python scripts/naver/blog/blog_scraper.py \
        --blog https://blog.naver.com/skyjwshin --pages 2 --csv

    # 증분 수집
    python scripts/naver/blog/blog_scraper.py \
        --blog https://blog.naver.com/skyjwshin --pages 3 --incremental
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.browser.agent.agent import BrowserAgent


def load_existing(path: Path) -> tuple[list[dict], set[str]]:
    """기존 파일에서 데이터와 log_no 세트 로드."""
    if not path.exists():
        return [], set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = {str(r.get("log_no", "")) for r in data if r.get("log_no")}
        return data, ids
    except Exception:  # noqa: BLE001 - 블로그 스크래퍼 캐시 JSON 로드(읽기전용) - 로드 실패 시 빈 리스트/집합으로 안전한 기본값 반환
        return [], set()


def save_json(data: list[dict], path: Path):
    """JSON 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(data: list[dict], path: Path):
    """CSV 저장."""
    if not data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["log_no", "title", "author", "date", "comment_count", "href", "body", "tags", "images", "comments"]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            r = dict(row)
            if isinstance(r.get("tags"), list):
                r["tags"] = ",".join(r["tags"])
            if isinstance(r.get("images"), list):
                r["images"] = ",".join(r["images"][:3])
            if isinstance(r.get("comments"), list):
                r["comments"] = str(len(r["comments"]))
            writer.writerow(r)


def _build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서."""
    parser = argparse.ArgumentParser(
        description="네이버 블로그 대량 수집 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--blog", default="", help="단일 블로그 URL")
    parser.add_argument("--blogs", default="", help="여러 블로그 URL (쉼표로 구분)")
    parser.add_argument("--keywords", default="", help="모니터링 키워드 (쉼표로 구분)")
    parser.add_argument("--search", default="", help="검색어")
    parser.add_argument("--track", default="", help="블로거 추적 URL")
    parser.add_argument("--pages", type=int, default=1, help="수집 페이지 수")
    parser.add_argument("--max", type=int, default=30, help="최대 수집 수")
    parser.add_argument("--category", default="", help="카테고리 ID")
    parser.add_argument("--full", action="store_true", help="본문+댓글+이미지 포함")
    parser.add_argument("--images", action="store_true", help="이미지 다운로드")
    parser.add_argument("--out", default="", help="저장 경로")
    parser.add_argument("--csv", action="store_true", help="CSV도 저장")
    parser.add_argument("--incremental", action="store_true", help="증분 수집")
    return parser


def _scrape_single_blog(agent, args, timestamp: str) -> None:
    """단일 블로그 수집."""
    blog_id = args.blog.rstrip("/").split("/")[-1]
    out_path = Path(args.out) if args.out else Path(f"data/scrape/blog_{blog_id}_{timestamp}.json")

    existing_data: list[dict] = []
    existing_ids: set[str] = set()
    if args.incremental and out_path.exists():
        existing_data, existing_ids = load_existing(out_path)
        print(f"기존 데이터: {len(existing_data)}개")

    all_posts = []
    seen_ids = set(existing_ids)

    print(f"\n수집 시작: {args.blog}")
    print(f"페이지: {args.pages} | full={args.full}")
    print(f"저장 경로: {out_path}\n")

    for page in range(1, args.pages + 1):
        print(f"[{page}/{args.pages}] 수집 중...")
        posts = agent.blog_posts(args.blog, category_no=args.category, page=page, max_posts=args.max)

        if not posts:
            print("  포스트 없음, 종료")
            break

        new_count = 0
        for i, post in enumerate(posts, 1):
            log_no = post.get("log_no", "")
            if log_no in seen_ids:
                continue

            if args.full and post.get("href"):
                detail = agent.blog_read_post(post["href"])
                post.update(
                    {
                        "body": detail.get("body", ""),
                        "tags": detail.get("tags", []),
                        "images": detail.get("images", []),
                        "comment_count": detail.get("comment_count", 0),
                        "comments": detail.get("comments", []),
                    }
                )

            seen_ids.add(log_no)
            all_posts.append(post)
            new_count += 1
            print(f"  {post['title'][:50]}")

        print(f"  신규: {new_count}개 (누계 {len(all_posts)}개)\n")

    final_data = existing_data + all_posts
    save_json(final_data, out_path)
    print(f"저장 완료: {out_path} ({len(final_data)}개)")

    if args.csv:
        csv_path = out_path.with_suffix(".csv")
        save_csv(final_data, csv_path)
        print(f"CSV 저장: {csv_path}")


def _scrape_bulk_blogs(agent, args, timestamp: str) -> None:
    """여러 블로그 수집."""
    blog_urls = [url.strip() for url in args.blogs.split(",")]
    out_path = Path(args.out) if args.out else Path(f"data/scrape/blogs_bulk_{timestamp}.json")

    print(f"\n여러 블로그 수집: {len(blog_urls)}개")
    all_data = agent.blog_bulk_collect(
        blog_urls,
        include_posts=True,
        include_comments=args.full,
        include_images=args.full,
        max_posts_each=args.max,
    )

    save_json(all_data, out_path)
    print(f"저장 완료: {out_path}")


def _monitor_keywords(agent, args, timestamp: str) -> None:
    """키워드 모니터링."""
    keywords = [kw.strip() for kw in args.keywords.split(",")]
    out_path = Path(args.out) if args.out else Path(f"data/scrape/keywords_{timestamp}.json")

    print(f"\n키워드 모니터링: {keywords}")
    results = agent.blog_monitor_keywords(keywords, page=1, max_each=args.max)

    save_json(results, out_path)
    print(f"저장 완료: {out_path}")


def _scrape_search(agent, args, timestamp: str) -> None:
    """검색 결과 수집."""
    out_path = Path(args.out) if args.out else Path(f"data/scrape/search_{args.search}_{timestamp}.json")

    print(f"\n검색 결과 수집: '{args.search}'")
    results = agent.blog_search_bulk(args.search, max_pages=args.pages, collect_post=args.full)

    save_json(results, out_path)
    print(f"저장 완료: {out_path} ({len(results)}개)")


def _track_blogger(agent, args, timestamp: str) -> None:
    """블로거 추적."""
    out_path = Path(args.out) if args.out else Path(f"data/scrape/track_{datetime.now().isoformat()}.json")

    print(f"\n블로거 추적: {args.track}")
    agent.blog_track_blogger(args.track, save_path=str(out_path))
    print(f"저장 완료: {out_path}")


def main():
    parser = _build_parser()

    args = parser.parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with BrowserAgent() as agent:
        # ── 단일 블로그 수집 ──────────────────────────────────────
        if args.blog:
            _scrape_single_blog(agent, args, timestamp)

        # ── 여러 블로그 수집 ──────────────────────────────────────
        elif args.blogs:
            _scrape_bulk_blogs(agent, args, timestamp)

        # ── 키워드 모니터링 ────────────────────────────────────────
        elif args.keywords:
            _monitor_keywords(agent, args, timestamp)

        # ── 검색 결과 수집 ────────────────────────────────────────
        elif args.search:
            _scrape_search(agent, args, timestamp)

        # ── 블로거 추적 ────────────────────────────────────────
        elif args.track:
            _track_blogger(agent, args, timestamp)

        else:
            parser.print_help()


if __name__ == "__main__":
    main()
