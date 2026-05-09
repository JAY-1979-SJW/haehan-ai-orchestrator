"""네이버 카페 탐색 스크립트.

사용법:
    # 카페 정보 + 게시판 목록
    python scripts/local_agent/naver_cafe_explorer.py info https://cafe.naver.com/0moo

    # 게시글 목록 (전체글보기)
    python scripts/local_agent/naver_cafe_explorer.py posts https://cafe.naver.com/0moo

    # 특정 게시판
    python scripts/local_agent/naver_cafe_explorer.py posts https://cafe.naver.com/0moo --board "건설 자유 게시판"

    # 페이지 지정
    python scripts/local_agent/naver_cafe_explorer.py posts https://cafe.naver.com/0moo --page 2

    # 여러 페이지 수집
    python scripts/local_agent/naver_cafe_explorer.py posts https://cafe.naver.com/0moo --pages 3

    # 인기글
    python scripts/local_agent/naver_cafe_explorer.py popular https://cafe.naver.com/0moo

    # 카페 내 검색
    python scripts/local_agent/naver_cafe_explorer.py search https://cafe.naver.com/0moo 노무

    # 게시글 본문 + 댓글
    python scripts/local_agent/naver_cafe_explorer.py article "https://cafe.naver.com/ArticleRead.nhn?clubid=10445200&articleid=585494"

    # JSON 출력
    python scripts/local_agent/naver_cafe_explorer.py posts https://cafe.naver.com/0moo --json

    # 내 카페 목록
    python scripts/local_agent/naver_cafe_explorer.py mycafes
"""

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_orchestrator.local_agent.browser.agent import BrowserAgent


def _print_posts(posts: list[dict], show_views: bool = True):
    if not posts:
        print("  (게시글 없음)")
        return
    for i, p in enumerate(posts, 1):
        cmt = f"[{p.get('comments', ''):>3}]" if p.get('comments') else "[   ]"
        author = (p.get('author') or '')[:10]
        date = (p.get('date') or '')
        views = f" 조회:{p.get('views','')}" if show_views and p.get('views') else ""
        title = p['title'][:50]
        print(f"  {i:3}. {cmt} {title:50} {author:12} {date}{views}")
    print(f"\n  총 {len(posts)}개")


def cmd_info(agent: BrowserAgent, cafe_url: str, as_json: bool):
    info = agent.cafe_info(cafe_url)
    if as_json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    print(f"카페명  : {info['name']}")
    print(f"운영자  : {info['manager']}")
    print(f"개설일  : {info['opened_at']}")
    print(f"등급    : {info['grade']}")
    print(f"멤버수  : {info['member_count']}")
    print(f"Club ID : {info['club_id']}")
    print(f"\n게시판 목록 ({len(info['boards'])}개):")
    for b in info['boards']:
        print(f"  - {b['name']:<30} menuid={b['menu_id']}")


def cmd_boards(agent: BrowserAgent, cafe_url: str, as_json: bool):
    boards = agent.cafe_boards(cafe_url)
    if as_json:
        print(json.dumps(boards, ensure_ascii=False, indent=2))
        return
    print(f"게시판 목록 ({len(boards)}개):")
    for i, b in enumerate(boards, 1):
        print(f"  {i:2}. {b['name']:<30} menuid={b['menu_id']}")


def cmd_posts(agent: BrowserAgent, cafe_url: str,
              board: str, page: int, max_pages: int,
              max_posts: int, as_json: bool):
    if max_pages > 1:
        posts = agent.cafe_posts_all_pages(cafe_url, board=board, max_pages=max_pages)
    else:
        posts = agent.cafe_posts(cafe_url, board=board, page=page, max_posts=max_posts)

    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return

    label = board if board != "전체글보기" else "전체글보기"
    print(f"[{label}] 게시글 목록 (page={page}):")
    _print_posts(posts)


def cmd_popular(agent: BrowserAgent, cafe_url: str, max_posts: int, as_json: bool):
    posts = agent.cafe_popular(cafe_url, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print("인기글 목록:")
    _print_posts(posts)


def cmd_search(agent: BrowserAgent, cafe_url: str, query: str,
               page: int, max_posts: int, as_json: bool):
    posts = agent.cafe_search(cafe_url, query, page=page, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"검색 결과: '{query}'")
    _print_posts(posts, show_views=False)


def cmd_article(agent: BrowserAgent, article_url: str, as_json: bool):
    r = agent.read_article(article_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"제목   : {r['title']}")
    print(f"게시판 : {r['board']}")
    print(f"작성자 : {r['author']}  {r['written_at']}")
    print(f"조회수 : {r['view_count']}  좋아요: {r['like_count']}  댓글: {r['comment_count']}")
    print(f"태그   : {', '.join(r['tags'])}")
    print(f"\n본문 ({len(r['body'])}자):")
    print(r['body'])
    if r['comments']:
        print(f"\n댓글 {len(r['comments'])}개:")
        for c in r['comments']:
            print(f"  [{c['author']}] {c['written_at']}")
            print(f"    {c['body']}")


def cmd_mycafes(agent: BrowserAgent, as_json: bool):
    cafes = agent.naver_cafe_list()
    if as_json:
        print(json.dumps(cafes, ensure_ascii=False, indent=2))
        return
    print(f"내 카페 목록 ({len(cafes)}개):")
    for i, c in enumerate(cafes, 1):
        print(f"  {i:3}. {c['text']}")


def main():
    parser = argparse.ArgumentParser(
        description="네이버 카페 탐색 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command",
        choices=["info", "boards", "posts", "popular", "search", "article", "mycafes"],
        help="실행할 명령")
    parser.add_argument("cafe_url", nargs="?", default="",
        help="카페 URL (article 명령 시 게시글 URL)")
    parser.add_argument("query", nargs="?", default="",
        help="검색어 (search 명령 전용)")
    parser.add_argument("--board", default="전체글보기",
        help="게시판명 또는 게시판 URL (기본: 전체글보기)")
    parser.add_argument("--page", type=int, default=1,
        help="페이지 번호 (기본: 1)")
    parser.add_argument("--pages", type=int, default=1,
        help="수집할 최대 페이지 수 (기본: 1)")
    parser.add_argument("--max", type=int, default=30,
        help="최대 수집 수 (기본: 30)")
    parser.add_argument("--json", action="store_true", dest="as_json",
        help="JSON 형식으로 출력")

    args = parser.parse_args()

    with BrowserAgent() as agent:
        if args.command == "mycafes":
            cmd_mycafes(agent, args.as_json)

        elif args.command == "info":
            if not args.cafe_url:
                parser.error("info 명령에는 카페 URL이 필요합니다")
            cmd_info(agent, args.cafe_url, args.as_json)

        elif args.command == "boards":
            if not args.cafe_url:
                parser.error("boards 명령에는 카페 URL이 필요합니다")
            cmd_boards(agent, args.cafe_url, args.as_json)

        elif args.command == "posts":
            if not args.cafe_url:
                parser.error("posts 명령에는 카페 URL이 필요합니다")
            cmd_posts(agent, args.cafe_url,
                      board=args.board, page=args.page,
                      max_pages=args.pages, max_posts=args.max,
                      as_json=args.as_json)

        elif args.command == "popular":
            if not args.cafe_url:
                parser.error("popular 명령에는 카페 URL이 필요합니다")
            cmd_popular(agent, args.cafe_url, max_posts=args.max, as_json=args.as_json)

        elif args.command == "search":
            if not args.cafe_url or not args.query:
                parser.error("search 명령에는 카페 URL과 검색어가 필요합니다")
            cmd_search(agent, args.cafe_url, args.query,
                       page=args.page, max_posts=args.max, as_json=args.as_json)

        elif args.command == "article":
            if not args.cafe_url:
                parser.error("article 명령에는 게시글 URL이 필요합니다")
            cmd_article(agent, args.cafe_url, args.as_json)


if __name__ == "__main__":
    main()
