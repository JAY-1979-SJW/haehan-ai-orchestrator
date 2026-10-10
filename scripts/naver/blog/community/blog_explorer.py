"""네이버 블로그 탐색 스크립트.

사용법:
    # 블로그 기본정보
    python scripts/naver/blog/blog_explorer.py info https://blog.naver.com/skyjwshin

    # 카테고리 목록
    python scripts/naver/blog/blog_explorer.py categories https://blog.naver.com/skyjwshin

    # 포스트 목록
    python scripts/naver/blog/blog_explorer.py posts https://blog.naver.com/skyjwshin
    python scripts/naver/blog/blog_explorer.py posts https://blog.naver.com/skyjwshin --category 10 --page 1 --max 30

    # 포스트 읽기
    python scripts/naver/blog/blog_explorer.py post "https://blog.naver.com/skyjwshin/223029..."

    # 포스트 이미지
    python scripts/naver/blog/blog_explorer.py images "https://blog.naver.com/skyjwshin/223029..."

    # 블로그 검색
    python scripts/naver/blog/blog_explorer.py search "파이썬" --page 1 --max 20

    # 방명록
    python scripts/naver/blog/blog_explorer.py guestbook https://blog.naver.com/skyjwshin --max 50

    # 이웃 목록
    python scripts/naver/blog/blog_explorer.py neighbors https://blog.naver.com/skyjwshin

    # 포스트 댓글
    python scripts/naver/blog/blog_explorer.py post-comments "https://blog.naver.com/skyjwshin/223029..." --max 100

    # 전체 댓글
    python scripts/naver/blog/blog_explorer.py all-comments https://blog.naver.com/skyjwshin --pages 5

    # 통계
    python scripts/naver/blog/blog_explorer.py stats https://blog.naver.com/skyjwshin

    # 태그 포스트
    python scripts/naver/blog/blog_explorer.py tag-posts https://blog.naver.com/skyjwshin --tag "개발"

    # 이웃 방문
    python scripts/naver/blog/blog_explorer.py visit-neighbors https://blog.naver.com/skyjwshin --max 10 --delay 2

    # 이웃 댓글
    python scripts/naver/blog/blog_explorer.py comment-neighbors https://blog.naver.com/skyjwshin --text "좋은 포스트네요!" --max 5

    # 이웃 공감
    python scripts/naver/blog/blog_explorer.py like-neighbors https://blog.naver.com/skyjwshin --max 10

    # 방문+공감+댓글
    python scripts/naver/blog/blog_explorer.py visit-and-comment https://blog.naver.com/skyjwshin --text "잘 봤습니다!" --max 5 --like

    # 이웃 활동
    python scripts/naver/blog/blog_explorer.py neighbor-activity https://blog.naver.com/skyjwshin --days 7

    # 사진 다운로드
    python scripts/naver/blog/blog_explorer.py download-images "https://blog.naver.com/skyjwshin/223029..." --out data/blog_images

    # 전체 사진 다운로드
    python scripts/naver/blog/blog_explorer.py download-all https://blog.naver.com/skyjwshin --out data/blog_images --pages 3

    # JSON 출력
    python scripts/naver/blog/blog_explorer.py posts https://blog.naver.com/skyjwshin --json
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.browser.agent.agent import BrowserAgent


def cmd_info(agent: BrowserAgent, blog_url: str, as_json: bool):
    r = agent.blog_info(blog_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"블로그  : {r['title']}")
    print(f"소개    : {r['description'][:100]}")
    print(f"이웃수  : {r['neighbor_count']}")
    print(f"오늘방문: {r['visitor_today']}")
    print(f"전체방문: {r['visitor_total']:,}")


def cmd_categories(agent: BrowserAgent, blog_url: str, as_json: bool):
    cats = agent.blog_categories(blog_url)
    if as_json:
        print(json.dumps(cats, ensure_ascii=False, indent=2))
        return
    print(f"카테고리 ({len(cats)}개):")
    for c in cats:
        print(f"  - {c['name']:20} categoryNo={c['category_no']:>4}  글:{c['post_count']:>3}개")


def cmd_posts(agent: BrowserAgent, blog_url: str, category_no: str, page: int, max_posts: int, as_json: bool):
    posts = agent.blog_posts(blog_url, category_no=category_no, page=page, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"포스트 목록 (page={page}, {len(posts)}개):")
    for i, p in enumerate(posts, 1):
        cmt = f"[댓글{p.get('comment_count', '?')}]" if p.get("comment_count") else ""
        print(f"  {i:2}. {p['title'][:50]:50} {p.get('date', '')} {cmt}")


def cmd_post(agent: BrowserAgent, post_url: str, as_json: bool):
    r = agent.blog_read_post(post_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"제목   : {r['title']}")
    print(f"작성자 : {r['author']}  {r['written_at']}")
    print(f"댓글   : {r['comment_count']}개  좋아요: {r['like_count']}")
    print(f"태그   : {', '.join(r['tags'])}")
    print(f"이미지 : {len(r['images'])}개")
    print(f"\n본문 ({len(r['body'])}자):")
    print(r["body"][:1000])
    if r["comments"]:
        print(f"\n댓글 {len(r['comments'])}개:")
        for c in r["comments"][:10]:
            print(f"  [{c['author']}] {c['written_at']}")
            print(f"    {c['body'][:80]}")


def cmd_images(agent: BrowserAgent, post_url: str, as_json: bool):
    images = agent.blog_post_images(post_url)
    if as_json:
        print(json.dumps(images, ensure_ascii=False, indent=2))
        return
    print(f"포스트 이미지 ({len(images)}개):")
    for i, img in enumerate(images, 1):
        src = img.get("src", "") if isinstance(img, dict) else img
        print(f"  {i}. {src[:80]}")


def cmd_search(agent: BrowserAgent, query: str, page: int, max_results: int, as_json: bool):
    results = agent.blog_search(query, page=page, max_results=max_results)
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(f"검색 결과: '{query}' (page={page}, {len(results)}개)")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r['title'][:50]:50} [{r['blog_id']}] {r['date']}")
        print(f"     {r['summary'][:80]}")


def cmd_guestbook(agent: BrowserAgent, blog_url: str, max_entries: int, as_json: bool):
    entries = agent.blog_guestbook(blog_url, max_entries=max_entries)
    if as_json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return
    print(f"방명록 ({len(entries)}개):")
    for e in entries:
        print(f"  [{e['written_at']}] {e['author']:15} {e['message'][:50]}")


def cmd_neighbors(agent: BrowserAgent, blog_url: str, max_neighbors: int, as_json: bool):
    neighbors = agent.blog_neighbors(blog_url, max_neighbors=max_neighbors)
    if as_json:
        print(json.dumps(neighbors, ensure_ascii=False, indent=2))
        return
    print(f"이웃 ({len(neighbors)}명):")
    for n in neighbors:
        mutual = "★" if n.get("is_mutual") else " "
        print(f"  {mutual} {n['nickname']:20} {n['blog_id']}")


def cmd_post_comments(agent: BrowserAgent, post_url: str, max_comments: int, as_json: bool):
    comments = agent.blog_post_comments(post_url, max_comments=max_comments)
    if as_json:
        print(json.dumps(comments, ensure_ascii=False, indent=2))
        return
    print(f"댓글 ({len(comments)}개):")
    for c in comments[:20]:
        print(f"  [{c['author']}] {c['written_at']}")
        print(f"    {c['body'][:80]}")


def cmd_all_comments(
    agent: BrowserAgent, blog_url: str, category_no: str, max_posts: int, max_comments_per_post: int, as_json: bool
):
    comments = agent.blog_all_comments(
        blog_url, category_no=category_no, max_posts=max_posts, max_comments_per_post=max_comments_per_post
    )
    if as_json:
        print(json.dumps(comments, ensure_ascii=False, indent=2))
        return
    print("\n=== 수집 완료 ===")
    print(f"전체 댓글: {len(comments)}개")

    # 포스트별 집계
    by_post: dict[Any, Any] = {}
    for c in comments:
        post_key = c.get("post_title", "")
        by_post[post_key] = by_post.get(post_key, 0) + 1

    print("\n포스트별 댓글수:")
    for title, cnt in sorted(by_post.items(), key=lambda x: -x[1])[:10]:
        print(f"  {title[:50]:50} {cnt}개")


def cmd_stats(agent: BrowserAgent, blog_url: str, as_json: bool):
    stats = agent.blog_stats_detail(blog_url)
    if as_json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    print("블로그 통계:")
    print(f"  오늘방문  : {stats['visitor_today']:,}")
    print(f"  주간방문  : {stats['visitor_week']:,}")
    print(f"  월간방문  : {stats['visitor_month']:,}")
    print(f"  전체방문  : {stats['visitor_total']:,}")
    print(f"  포스트수  : {stats['post_count']}")
    print(f"  댓글수    : {stats['comment_count']}")
    print(f"  이웃수    : {stats['neighbor_count']}")
    if stats.get("top_posts"):
        print("\n인기 포스트:")
        for p in stats["top_posts"][:5]:
            print(f"  - {p['title'][:50]:50} 조회:{p.get('views', 0)}")


def cmd_tag_posts(agent: BrowserAgent, blog_url: str, tag: str, max_posts: int, as_json: bool):
    posts = agent.blog_tag_posts(blog_url, tag=tag, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"태그 '{tag}' 포스트 ({len(posts)}개):")
    for i, p in enumerate(posts, 1):
        print(f"  {i:2}. {p['title'][:50]:50} {p.get('date', '')}")


def cmd_visit_neighbors(agent: BrowserAgent, blog_url: str, max_neighbors: int, delay: float, as_json: bool):
    print(f"이웃 {max_neighbors}명 방문 시작 (간격 {delay}초)...")
    results = agent.blog_visit_neighbors(blog_url, max_neighbors=max_neighbors, delay=delay)
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    success = sum(1 for r in results if r["visit_ok"])
    print("\n=== 완료 ===")
    print(f"성공: {success}/{len(results)}")


def cmd_comment_neighbors(
    agent: BrowserAgent, blog_url: str, comment_text: str, max_neighbors: int, delay: float, as_json: bool
):
    print(f"이웃 {max_neighbors}명에게 댓글 달기 시작...")
    results = agent.blog_comment_neighbors(blog_url, comment_text, max_neighbors=max_neighbors, delay=delay)
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    success = sum(1 for r in results if r["ok"])
    print("\n=== 완료 ===")
    print(f"댓글 작성: {success}/{len(results)}")


def cmd_like_neighbors(agent: BrowserAgent, blog_url: str, max_neighbors: int, delay: float, as_json: bool):
    print(f"이웃 {max_neighbors}명 포스트 공감 시작...")
    results = agent.blog_like_neighbors(blog_url, max_neighbors=max_neighbors, delay=delay)
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    success = sum(1 for r in results if r["ok"])
    print("\n=== 완료 ===")
    print(f"공감: {success}/{len(results)}")


def cmd_visit_and_comment(agent: BrowserAgent, args: argparse.Namespace):
    # 2026-09-29 STD-08: PLR0913(인자 7>6) — 나머지 _run_* 와 같은 방식으로 argparse.Namespace
    # 하나로 묶었다(호출부가 이 파일 안의 _run_visit_and_comment 하나뿐이라 안전, 값은 동일).
    blog_url, comment_text, max_neighbors, also_like, delay, as_json = (
        args.blog_url,
        args.text,
        args.max,
        args.like,
        args.delay,
        args.as_json,
    )
    print(f"이웃 {max_neighbors}명 방문/공감/댓글 시작...")
    results = agent.blog_visit_and_comment(
        blog_url, comment_text, max_neighbors=max_neighbors, also_like=also_like, delay=delay
    )
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print("\n=== 완료 ===")
    for r in results:
        visited = "✓" if r.get("visited") else "✗"
        liked = "♥" if r.get("liked") else " "
        commented = "💬" if r.get("commented") else " "
        print(f"  [{visited}] {liked}{commented} {r['blog_id']}")


def cmd_neighbor_activity(agent: BrowserAgent, blog_url: str, days: int, as_json: bool):
    activities = agent.blog_neighbor_activity(blog_url, days=days)
    if as_json:
        print(json.dumps(activities, ensure_ascii=False, indent=2))
        return
    print(f"최근 {days}일 이웃 활동:")
    active = [a for a in activities if a["is_active"]]
    inactive = [a for a in activities if not a["is_active"]]

    print(f"\n활동 중 ({len(active)}명):")
    for a in active:
        print(f"  {a['nickname']:20} 최근글: {a['last_post_title'][:40]}")

    if inactive:
        print(f"\n활동 없음 ({len(inactive)}명):")
        for a in inactive[:10]:
            print(f"  {a['nickname']}")


def cmd_download_images(agent: BrowserAgent, post_url: str, out_dir: str, as_json: bool):
    print("포스트 이미지 다운로드 중...")
    result = agent.blog_download_images(post_url, save_dir=out_dir)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("\n=== 완료 ===")
    print(f"다운로드: {result['downloaded']}개")
    print(f"실패     : {result['failed']}개")
    print(f"저장위치 : {result['save_dir']}")


def cmd_download_all(agent: BrowserAgent, blog_url: str, out_dir: str, category_no: str, max_pages: int, as_json: bool):
    print("블로그 전체 이미지 다운로드 시작...")
    result = agent.blog_download_all_images(blog_url, save_dir=out_dir, category_no=category_no, max_pages=max_pages)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("\n=== 완료 ===")
    print(f"포스트   : {result['total_posts']}개")
    print(f"다운로드 : {result['downloaded']}개")
    print(f"실패     : {result['failed']}개")
    print(f"저장위치 : {result['save_dir']}")


_ALL_COMMANDS = [
    "info",
    "categories",
    "posts",
    "post",
    "images",
    "search",
    "guestbook",
    "neighbors",
    "post-comments",
    "all-comments",
    "stats",
    "tag-posts",
    "visit-neighbors",
    "comment-neighbors",
    "like-neighbors",
    "visit-and-comment",
    "neighbor-activity",
    "download-images",
    "download-all",
]


def _run_info(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("info 명령에는 블로그 URL이 필요합니다")
    cmd_info(agent, args.blog_url, args.as_json)


def _run_categories(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("categories 명령에는 블로그 URL이 필요합니다")
    cmd_categories(agent, args.blog_url, args.as_json)


def _run_posts(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("posts 명령에는 블로그 URL이 필요합니다")
    cmd_posts(agent, args.blog_url, args.category, args.page, args.max, args.as_json)


def _run_post(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("post 명령에는 포스트 URL이 필요합니다")
    cmd_post(agent, args.blog_url, args.as_json)


def _run_images(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("images 명령에는 포스트 URL이 필요합니다")
    cmd_images(agent, args.blog_url, args.as_json)


def _run_search(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("search 명령에는 검색어가 필요합니다")
    cmd_search(agent, args.blog_url, args.page, args.max, args.as_json)


def _run_guestbook(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("guestbook 명령에는 블로그 URL이 필요합니다")
    cmd_guestbook(agent, args.blog_url, args.max, args.as_json)


def _run_neighbors(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("neighbors 명령에는 블로그 URL이 필요합니다")
    cmd_neighbors(agent, args.blog_url, args.max, args.as_json)


def _run_post_comments(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("post-comments 명령에는 포스트 URL이 필요합니다")
    cmd_post_comments(agent, args.blog_url, args.max, args.as_json)


def _run_all_comments(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("all-comments 명령에는 블로그 URL이 필요합니다")
    cmd_all_comments(agent, args.blog_url, args.category, args.pages, args.max, args.as_json)


def _run_stats(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("stats 명령에는 블로그 URL이 필요합니다")
    cmd_stats(agent, args.blog_url, args.as_json)


def _run_tag_posts(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url or not args.tag:
        parser.error("tag-posts 명령에는 블로그 URL과 --tag이 필요합니다")
    cmd_tag_posts(agent, args.blog_url, args.tag, args.max, args.as_json)


def _run_visit_neighbors(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("visit-neighbors 명령에는 블로그 URL이 필요합니다")
    cmd_visit_neighbors(agent, args.blog_url, args.max, args.delay, args.as_json)


def _run_comment_neighbors(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url or not args.text:
        parser.error("comment-neighbors 명령에는 블로그 URL과 --text이 필요합니다")
    cmd_comment_neighbors(agent, args.blog_url, args.text, args.max, args.delay, args.as_json)


def _run_like_neighbors(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("like-neighbors 명령에는 블로그 URL이 필요합니다")
    cmd_like_neighbors(agent, args.blog_url, args.max, args.delay, args.as_json)


def _run_visit_and_comment(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url or not args.text:
        parser.error("visit-and-comment 명령에는 블로그 URL과 --text이 필요합니다")
    cmd_visit_and_comment(agent, args)


def _run_neighbor_activity(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("neighbor-activity 명령에는 블로그 URL이 필요합니다")
    cmd_neighbor_activity(agent, args.blog_url, args.days, args.as_json)


def _run_download_images(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("download-images 명령에는 포스트 URL이 필요합니다")
    cmd_download_images(agent, args.blog_url, args.out, args.as_json)


def _run_download_all(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.blog_url:
        parser.error("download-all 명령에는 블로그 URL이 필요합니다")
    cmd_download_all(agent, args.blog_url, args.out, args.category, args.pages, args.as_json)


# cmd 문자열 → 실행 함수. 원래 main() 의 if/elif cmd == ... 순서를 그대로 옮긴 것 — 동작은 동일하다.
# (2026-09-29 STD-08: if/elif 19개가 mccabe/pylint 에 "분기 19개"로 그대로 잡혀 dict 조회로 바꿨다.)
_RUNNERS: dict[str, Callable[[BrowserAgent, argparse.ArgumentParser, argparse.Namespace], None]] = {
    "info": _run_info,
    "categories": _run_categories,
    "posts": _run_posts,
    "post": _run_post,
    "images": _run_images,
    "search": _run_search,
    "guestbook": _run_guestbook,
    "neighbors": _run_neighbors,
    "post-comments": _run_post_comments,
    "all-comments": _run_all_comments,
    "stats": _run_stats,
    "tag-posts": _run_tag_posts,
    "visit-neighbors": _run_visit_neighbors,
    "comment-neighbors": _run_comment_neighbors,
    "like-neighbors": _run_like_neighbors,
    "visit-and-comment": _run_visit_and_comment,
    "neighbor-activity": _run_neighbor_activity,
    "download-images": _run_download_images,
    "download-all": _run_download_all,
}


def main():
    parser = argparse.ArgumentParser(
        description="네이버 블로그 탐색 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command", choices=_ALL_COMMANDS)
    parser.add_argument("blog_url", nargs="?", default="")
    parser.add_argument("--category", default="", help="카테고리 ID")
    parser.add_argument("--tag", default="", help="태그")
    parser.add_argument("--text", default="", help="댓글/방명록 텍스트")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--pages", type=int, default=1, help="수집 페이지 수")
    parser.add_argument("--max", type=int, default=30, help="최대 수집 수")
    parser.add_argument("--days", type=int, default=7, help="일 수")
    parser.add_argument("--delay", type=float, default=2.0, help="작업 간 대기 (초)")
    parser.add_argument("--like", action="store_true", help="공감 포함")
    parser.add_argument("--out", default="data/blog_images", help="저장 경로")
    parser.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args()

    with BrowserAgent() as agent:
        _RUNNERS[args.command](agent, parser, args)


if __name__ == "__main__":
    main()
