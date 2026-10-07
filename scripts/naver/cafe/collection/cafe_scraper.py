"""네이버 카페 스크래퍼.

게시글 목록 + 본문 + 댓글을 수집해 JSON / CSV로 저장.
증분 수집(이미 수집된 articleid 스킵), 중단 후 재개 지원.

사용법:
    # 전체글보기 3페이지 수집 (목록만)
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --pages 3

    # 특정 게시판, 본문+댓글 포함
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo \
        --board "건설 자유 게시판" \
        --pages 5 --full

    # 최대 게시글 수 제한
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --pages 10 --max-articles 100

    # 저장 경로 지정
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --pages 3 \
        --out data/my_scrape.json

    # CSV 저장
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --pages 3 --csv

    # 증분 수집 (기존 파일에 없는 글만)
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --pages 3 --incremental

    # 키워드 검색 결과 수집
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --query 노무 --pages 5 --full

    # 인기글 수집
    python scripts/naver/cafe/cafe_scraper.py \
        --cafe https://cafe.naver.com/0moo --popular
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.common.browser_js_dir import JS_DIR

if TYPE_CHECKING:  # 엔진 ↔ 믹스인 import 순환을 피하려고 타입 힌트로만 쓰고 실제 사용은 main 안에서 불러온다(T4 C12a)
    from scripts.browser.agent.agent import BrowserAgent


def _load_js(name: str) -> str:
    return (JS_DIR / name).read_text(encoding="utf-8")


def _extract_article_id(href: str) -> str:
    m = re.search(r"articles/(\d+)|articleid=(\d+)", href)
    return m.group(1) or m.group(2) if m else ""


def _board_list_url(club_id: str, menu_id: str, page: int) -> str:
    base = f"https://cafe.naver.com/ArticleList.nhn?search.clubid={club_id}"
    if menu_id:
        base += f"&search.menuid={menu_id}"
    base += f"&search.boardtype=L&search.page={page}"
    return base


def _search_url(club_id: str, query: str, page: int) -> str:
    import urllib.parse

    q = urllib.parse.quote(query)
    return f"https://cafe.naver.com/f-e/cafes/{club_id}/menus/0?viewType=L&ta=ARTICLE_COMMENT&page={page}&q={q}"


def _popular_url(club_id: str) -> str:
    return f"https://cafe.naver.com/f-e/cafes/{club_id}/popular"


def scrape_posts_page(agent: BrowserAgent, url: str) -> list[dict]:
    """단일 페이지에서 게시글 목록 수집."""
    agent.go(url)
    time.sleep(2)
    js = _load_js("extract_cafe_posts.js")
    posts = []
    seen = set()
    for frame in agent.page.frames:
        try:
            results = frame.evaluate(js)
            for p in results:
                aid = _extract_article_id(p.get("href", ""))
                if aid and aid not in seen:
                    seen.add(aid)
                    p["article_id"] = aid
                    posts.append(p)
        except Exception:  # noqa: BLE001 - 네이버 카페 게시글 읽기전용 스크래핑 — 개별 게시글 파싱 실패는 continue로 건너뛰고, 캐시 로드 실패는 빈 목록/빈 set으로 폴백, 쓰기 없음
            continue
    return posts


def scrape_article(agent: BrowserAgent, href: str, delay: float = 1.5) -> dict:
    """게시글 본문 + 댓글 수집."""
    time.sleep(delay)
    return agent.read_article(href)


def load_existing(path: Path) -> tuple[list[dict], set[str]]:
    """기존 저장 파일에서 데이터와 article_id 집합 로드."""
    if not path.exists():
        return [], set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = {r.get("article_id", "") for r in data if r.get("article_id")}
        return data, ids
    except Exception:  # noqa: BLE001 - 네이버 카페 게시글 읽기전용 스크래핑 — 개별 게시글 파싱 실패는 continue로 건너뛰고, 캐시 로드 실패는 빈 목록/빈 set으로 폴백, 쓰기 없음
        return [], set()


def save_json(data: list[dict], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(data: list[dict], path: Path):
    if not data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    # 목록용 필드 (본문은 별도 컬럼)
    fields = [
        "article_id",
        "title",
        "author",
        "date",
        "views",
        "comments",
        "href",
        "board",
        "written_at",
        "view_count",
        "like_count",
        "comment_count",
        "tags",
        "body",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in data:
            r = dict(row)
            if isinstance(r.get("tags"), list):
                r["tags"] = ",".join(r["tags"])
            if isinstance(r.get("comments"), list):  # full 모드의 comments
                r["comment_count"] = len(r["comments"])
                r["comments"] = ""
            writer.writerow(r)


def _resolve_board(agent: BrowserAgent, cafe_url: str, board_name: str, club_id: str) -> tuple[str, str]:
    """게시판명 → (menu_id, board_label)."""
    if not board_name or board_name == "전체글보기":
        return "", "전체글보기"

    # 사이드바 링크에서 menuid 추출
    agent.go(cafe_url)
    time.sleep(2)
    links = agent.extract_links(filter_href="ArticleList")
    for l in links:
        if board_name in l["text"]:
            m = re.search(r"menuid=(\d+)", l["href"])
            if m:
                return m.group(1), l["text"].strip()

    print(f"  [경고] 게시판 '{board_name}'을 찾지 못했습니다. 전체글보기로 대체합니다.")
    return "", "전체글보기"


def _build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서."""
    parser = argparse.ArgumentParser(
        description="네이버 카페 스크래퍼",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--cafe", required=True, help="카페 URL")
    parser.add_argument("--board", default="전체글보기", help="게시판명 (기본: 전체글보기)")
    parser.add_argument("--query", default="", help="검색 키워드 (지정 시 검색 결과 수집)")
    parser.add_argument("--popular", action="store_true", help="인기글 수집")
    parser.add_argument("--pages", type=int, default=1, help="수집할 페이지 수 (기본: 1)")
    parser.add_argument("--max-articles", type=int, default=0, help="최대 게시글 수 (0=무제한)")
    parser.add_argument("--full", action="store_true", help="본문 + 댓글 포함 수집 (느림)")
    parser.add_argument("--delay", type=float, default=1.5, help="게시글 간 대기(초, 기본: 1.5)")
    parser.add_argument("--out", default="", help="저장 경로 (기본: data/scrape/<카페명>_<날짜>.json)")
    parser.add_argument("--csv", action="store_true", help="CSV도 함께 저장")
    parser.add_argument("--incremental", action="store_true", help="기존 파일에 없는 글만 수집")
    return parser


def _resolve_out_path(args, board_label: str, timestamp: str) -> Path:
    """출력 경로 결정."""
    cafe_slug = args.cafe.rstrip("/").split("/")[-1]
    if args.query:
        label = f"search_{args.query}"
    elif args.popular:
        label = "popular"
    else:
        label = re.sub(r"[^\w가-힣]", "_", board_label)[:20]

    out_path = Path(args.out) if args.out else Path(f"data/scrape/{cafe_slug}_{label}_{timestamp}.json")
    return out_path


def _collect_popular(agent, club_id: str, seen_ids: set[str], all_posts: list[dict]) -> None:
    """인기글 수집."""
    print("인기글 수집 중...")
    url = _popular_url(club_id)
    page_posts = scrape_posts_page(agent, url)
    for p in page_posts:
        aid = p.get("article_id", "")
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        all_posts.append(p)
    print(f"  인기글 {len(all_posts)}개 수집")


def _collect_board_pages(  # noqa: PLR0913 - main() 에서만 호출하는 내부 분할 헬퍼(인자 묶음 시 동작 위험)
    agent, args, club_id: str, menu_id: str, seen_ids: set[str], existing_ids: set[str], all_posts: list[dict]
) -> None:
    """게시판/검색 목록 페이지 순회 수집."""
    stop = False

    for page_num in range(1, args.pages + 1):
        if stop:
            break

        if args.query:
            url = _search_url(club_id, args.query, page_num)
        else:
            url = _board_list_url(club_id, menu_id, page_num)

        print(f"[{page_num}/{args.pages}] {url}")
        page_posts = scrape_posts_page(agent, url)

        if not page_posts:
            print("  → 게시글 없음, 수집 종료")
            break

        new_count = 0
        for p in page_posts:
            aid = p.get("article_id", "")
            if not aid or aid in seen_ids:
                if args.incremental and aid in existing_ids:
                    print(f"  → 증분: 기존 article_id={aid} 도달, 수집 중단")
                    stop = True
                    break
                continue
            seen_ids.add(aid)
            all_posts.append(p)
            new_count += 1

            if args.max_articles and len(all_posts) >= args.max_articles:
                print(f"  → max-articles={args.max_articles} 도달")
                stop = True
                break

        print(f"  → 신규 {new_count}개 (누계 {len(all_posts)}개)")


def _collect_full_bodies(agent, args, all_posts: list[dict]) -> None:
    """본문 + 댓글 수집 (full 모드)."""
    if args.full and all_posts:
        print(f"\n본문 수집: {len(all_posts)}개 게시글...")
        for i, post in enumerate(all_posts, 1):
            href = post.get("href", "")
            if not href:
                continue
            print(f"  [{i}/{len(all_posts)}] {post['title'][:40]}...")
            try:
                detail = scrape_article(agent, href, delay=args.delay)
                # 목록 정보 보존 + 상세 정보 병합
                post.update(
                    {
                        "board": detail.get("board", ""),
                        "written_at": detail.get("written_at", ""),
                        "view_count": detail.get("view_count", ""),
                        "like_count": detail.get("like_count", ""),
                        "comment_count": detail.get("comment_count", 0),
                        "tags": detail.get("tags", []),
                        "body": detail.get("body", ""),
                        "comments": detail.get("comments", []),
                    }
                )
            except Exception as e:  # noqa: BLE001 - 네이버 카페 게시글 읽기전용 스크래핑 — 개별 게시글 파싱 실패는 continue로 건너뛰고, 캐시 로드 실패는 빈 목록/빈 set으로 폴백, 쓰기 없음
                print(f"    [오류] {e}")
                post["body"] = ""
                post["comments"] = []


def _print_collect_summary(args, all_posts: list[dict], final_data: list[dict]) -> None:
    """수집 요약 출력."""
    print("\n=== 수집 요약 ===")
    print(f"신규 수집: {len(all_posts)}개")
    print(f"전체 저장: {len(final_data)}개")
    if all_posts:
        dates = [
            p.get("date") or p.get("written_at") or "" for p in all_posts if p.get("date") or p.get("written_at")
        ]
        if dates:
            print(f"날짜 범위: {min(dates)} ~ {max(dates)}")
        if args.full:
            with_body = sum(1 for p in all_posts if p.get("body"))
            print(f"본문 수집: {with_body}개")


def main():
    parser = _build_parser()
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        # club_id 추출
        agent.go(args.cafe)
        time.sleep(2)
        club_id = agent._get_club_id(args.cafe)
        if not club_id:
            print("[오류] club_id를 찾을 수 없습니다.")
            sys.exit(1)
        print(f"카페 club_id: {club_id}")

        # 게시판 menuid 결정
        menu_id = ""
        board_label = "전체글보기"
        if not args.query and not args.popular:
            menu_id, board_label = _resolve_board(agent, args.cafe, args.board, club_id)

        # 출력 경로 결정
        out_path = _resolve_out_path(args, board_label, timestamp)

        # 증분 모드: 기존 데이터 로드
        existing_data, existing_ids = [], set()
        if args.incremental and out_path.exists():
            existing_data, existing_ids = load_existing(out_path)
            print(f"기존 데이터: {len(existing_data)}개 (article_id {len(existing_ids)}개)")

        # 수집 시작
        all_posts: list[dict] = []
        seen_ids: set[str] = set(existing_ids)

        print(f"\n수집 시작: {board_label} | pages={args.pages} | full={args.full}")
        print(f"저장 경로: {out_path}\n")

        if args.popular:
            # 인기글
            _collect_popular(agent, club_id, seen_ids, all_posts)

        else:
            _collect_board_pages(agent, args, club_id, menu_id, seen_ids, existing_ids, all_posts)

        # 본문 + 댓글 수집 (full 모드)
        _collect_full_bodies(agent, args, all_posts)

        # 최종 데이터 = 기존 + 신규
        final_data = existing_data + all_posts

        # 저장
        save_json(final_data, out_path)
        print(f"\n저장 완료: {out_path} ({len(final_data)}개)")

        if args.csv:
            csv_path = out_path.with_suffix(".csv")
            save_csv(final_data, csv_path)
            print(f"CSV 저장: {csv_path}")

        # 요약 출력
        _print_collect_summary(args, all_posts, final_data)


if __name__ == "__main__":
    main()
