"""네이버 카페 탐색 스크립트.

사용법:
    # 카페 정보 + 게시판 목록
    python scripts/naver/cafe/cafe_explorer.py info https://cafe.naver.com/0moo

    # 게시글 목록 (전체글보기)
    python scripts/naver/cafe/cafe_explorer.py posts https://cafe.naver.com/0moo

    # 특정 게시판
    python scripts/naver/cafe/cafe_explorer.py posts https://cafe.naver.com/0moo --board "건설 자유 게시판"

    # 페이지 지정
    python scripts/naver/cafe/cafe_explorer.py posts https://cafe.naver.com/0moo --page 2

    # 여러 페이지 수집
    python scripts/naver/cafe/cafe_explorer.py posts https://cafe.naver.com/0moo --pages 3

    # 인기글
    python scripts/naver/cafe/cafe_explorer.py popular https://cafe.naver.com/0moo

    # 카페 내 검색
    python scripts/naver/cafe/cafe_explorer.py search https://cafe.naver.com/0moo 노무

    # 게시글 본문 + 댓글 + 첨부파일
    python scripts/naver/cafe/cafe_explorer.py article "https://cafe.naver.com/ArticleRead.nhn?clubid=10445200&articleid=585494"

    # 사진 게시판
    python scripts/naver/cafe/cafe_explorer.py photos https://cafe.naver.com/0moo --board "건설시공사진자료실"

    # 출석체크 목록
    python scripts/naver/cafe/cafe_explorer.py attendance https://cafe.naver.com/0moo

    # 가입인사 목록
    python scripts/naver/cafe/cafe_explorer.py greetings https://cafe.naver.com/0moo

    # 등업 신청 현황
    python scripts/naver/cafe/cafe_explorer.py levelup https://cafe.naver.com/0moo

    # 멤버 목록
    python scripts/naver/cafe/cafe_explorer.py members https://cafe.naver.com/0moo

    # 멤버 프로필
    python scripts/naver/cafe/cafe_explorer.py profile "https://cafe.naver.com/f-e/cafes/10445200/members/XXXX"

    # 좋아요한 글
    python scripts/naver/cafe/cafe_explorer.py liked https://cafe.naver.com/0moo

    # 스크랩한 글
    python scripts/naver/cafe/cafe_explorer.py scrapped https://cafe.naver.com/0moo

    # 앨범 (사진 게시판, GraphQL BFF)
    python scripts/naver/cafe/cafe_explorer.py album https://cafe.naver.com/0moo

    # 투표 목록
    python scripts/naver/cafe/cafe_explorer.py polls https://cafe.naver.com/0moo

    # 캘린더 일정 (이번 달)
    python scripts/naver/cafe/cafe_explorer.py calendar https://cafe.naver.com/0moo

    # 특정 월 캘린더
    python scripts/naver/cafe/cafe_explorer.py calendar https://cafe.naver.com/0moo --year 2026 --month 5

    # 이웃(구독) 멤버 목록
    python scripts/naver/cafe/cafe_explorer.py neighbors https://cafe.naver.com/0moo

    # JSON 출력
    python scripts/naver/cafe/cafe_explorer.py posts https://cafe.naver.com/0moo --json

    # 내 카페 목록
    python scripts/naver/cafe/cafe_explorer.py mycafes
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 엔진 ↔ 믹스인 import 순환을 피하려고 타입 힌트로만 쓰고 실제 사용은 main 안에서 불러온다(T4 C12a)
    from scripts.browser.agent.agent import BrowserAgent


def _print_posts(posts: list[dict], show_views: bool = True):
    if not posts:
        print("  (게시글 없음)")
        return
    for i, p in enumerate(posts, 1):
        cmt = f"[{p.get('comments', ''):>3}]" if p.get("comments") else "[   ]"
        author = (p.get("author") or "")[:10]
        date = p.get("date") or ""
        views = f" 조회:{p.get('views', '')}" if show_views and p.get("views") else ""
        title = p["title"][:50]
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
    for b in info["boards"]:
        print(f"  - {b['name']:<30} menuid={b['menu_id']}")


def cmd_boards(agent: BrowserAgent, cafe_url: str, as_json: bool):
    boards = agent.cafe_boards(cafe_url)
    if as_json:
        print(json.dumps(boards, ensure_ascii=False, indent=2))
        return
    print(f"게시판 목록 ({len(boards)}개):")
    for i, b in enumerate(boards, 1):
        print(f"  {i:2}. {b['name']:<30} menuid={b['menu_id']}")


def cmd_posts(agent: BrowserAgent, args: argparse.Namespace):
    # 2026-09-29 STD-08: PLR0913(인자 7>6) — 유일한 호출부(_run_posts)와 같은 방식으로
    # argparse.Namespace 하나로 묶었다(호출부가 이 파일 안에 하나뿐이라 안전).
    cafe_url = args.cafe_url
    board = args.board or "전체글보기"  # 원래 _run_posts 에서 계산하던 것과 동일
    page, max_pages, max_posts, as_json = args.page, args.pages, args.max, args.as_json
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


def cmd_search(agent: BrowserAgent, cafe_url: str, query: str, page: int, max_posts: int, as_json: bool):
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
    print(r["body"])
    if r["comments"]:
        print(f"\n댓글 {len(r['comments'])}개:")
        for c in r["comments"]:
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


def cmd_attendance(agent: BrowserAgent, cafe_url: str, as_json: bool):
    r = agent.cafe_attendance(cafe_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"출석체크 {r['date']}  오늘 출석: {r['today_count']}명")
    for rec in r.get("records", [])[:20]:
        msg = f"  {rec['message'][:30]}" if rec.get("message") else ""
        print(f"  [{rec['written_at']}] {rec['author']}{msg}")


def cmd_greetings(agent: BrowserAgent, cafe_url: str, max_posts: int, as_json: bool):
    posts = agent.cafe_greetings(cafe_url, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"가입인사 {len(posts)}개:")
    for p in posts:
        print(f"  [{p['written_at']}] {p['author']:15} {p['preview'][:40]}")


def cmd_levelup(agent: BrowserAgent, cafe_url: str, as_json: bool):
    r = agent.cafe_levelup_status(cafe_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    stats = r.get("my_stats", {})
    if stats:
        print(
            f"내 활동: 게시글 {stats.get('article_count', 0)}개 | "
            f"댓글 {stats.get('comment_count', 0)}개 | "
            f"좋아요 {stats.get('like_count', 0)}개 | "
            f"출석 {stats.get('attend_count', 0)}회 | "
            f"가입일 {stats.get('joined_at', '')}"
        )
    print(f"등업신청 가능: {'예' if r['can_apply'] else '아니오'}")
    apps = r.get("applications", [])
    if apps:
        print(f"신청 목록 ({len(apps)}건):")
        for a in apps:
            print(f"  {a['applicant']:15} {a['target_grade']:10} → {a['current_grade']}")


def cmd_members(agent: BrowserAgent, cafe_url: str, max_members: int, as_json: bool):
    members = agent.cafe_members(cafe_url, max_members=max_members)
    if as_json:
        print(json.dumps(members, ensure_ascii=False, indent=2))
        return
    print(f"멤버 목록 ({len(members)}명):")
    for i, m in enumerate(members, 1):
        print(f"  {i:3}. {m['nickname']:20} {m.get('grade', '')}")


def cmd_profile(agent: BrowserAgent, member_url: str, as_json: bool):
    r = agent.cafe_member_profile(member_url)
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"닉네임  : {r['nickname']}  ({r.get('masked_id', '')})")
    print(
        f"방문수  : {r.get('visit_count', 0):,}  |  작성글: {r.get('article_count', 0):,}  |  구독멤버: {r.get('subscriber_count', 0):,}"
    )
    arts = r.get("recent_articles", [])
    if arts:
        print(f"\n최근 게시글 {len(arts)}개:")
        for a in arts:
            print(f"  [{a['written_at']}] {a['title'][:50]:50} 조회:{a['views']}")


def cmd_photos(agent: BrowserAgent, cafe_url: str, board: str, max_posts: int, as_json: bool):
    posts = agent.cafe_photo_posts(cafe_url, board=board, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    label = board if board else "사진게시판"
    print(f"[{label}] 사진 게시글 {len(posts)}개:")
    _print_posts(posts)


def cmd_liked(agent: BrowserAgent, cafe_url: str, max_posts: int, as_json: bool):
    posts = agent.cafe_liked_articles(cafe_url, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"좋아요한 글 {len(posts)}개:")
    _print_posts(posts)


def cmd_scrapped(agent: BrowserAgent, cafe_url: str, max_posts: int, as_json: bool):
    posts = agent.cafe_scrapped_articles(cafe_url, max_posts=max_posts)
    if as_json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
        return
    print(f"스크랩한 글 {len(posts)}개:")
    _print_posts(posts)


def cmd_album(agent: BrowserAgent, cafe_url: str, menu_id: str, page: int, max_posts: int, as_json: bool):
    result = agent.cafe_album(cafe_url, menu_id=menu_id, page=page, per_page=max_posts)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    items = result.get("items", [])
    total = result.get("total_count", len(items))
    print(f"앨범 (전체 {total:,}개 중 {len(items)}개):")
    for i, it in enumerate(items, 1):
        thumb = " [썸네일O]" if it.get("thumb_url") else ""
        print(
            f"  {i:3}. {it['title'][:50]:50} {it.get('author', ''):12} "
            f"{it.get('written_at', '')} 조회:{it.get('views', 0)}{thumb}"
        )


def cmd_polls(agent: BrowserAgent, cafe_url: str, page: int, max_polls: int, as_json: bool):
    result = agent.cafe_polls(cafe_url, page=page, per_page=max_polls)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    items = result.get("items", [])
    total = result.get("total_count", len(items))
    print(f"투표 목록 (전체 {total:,}개 중 {len(items)}개):")
    for i, it in enumerate(items, 1):
        status = it.get("status", "")
        participants = it.get("participants", 0)
        end = it.get("end_date", "")
        print(f"  {i:3}. [{status:6}] {it['title'][:45]:45} 참여:{participants:>4}명  마감:{end}")
        for opt in (it.get("options") or [])[:3]:
            print(f"         └ {opt['text'][:30]:30} {opt['votes']:>4}표")


def cmd_calendar(agent: BrowserAgent, cafe_url: str, year: int, month: int, as_json: bool):
    events = agent.cafe_calendar(cafe_url, year=year, month=month)
    if as_json:
        print(json.dumps(events, ensure_ascii=False, indent=2))
        return
    import datetime as _dt

    now = _dt.date.today()
    y = year or now.year
    m = month or now.month
    print(f"캘린더 {y}년 {m}월 일정 ({len(events)}건):")
    for ev in events:
        all_day = " [종일]" if ev.get("is_all_day") else ""
        print(f"  {ev['start_date']} ~ {ev['end_date']}  {ev['title'][:40]}{all_day}  ({ev.get('author', '')})")


def cmd_neighbors(agent: BrowserAgent, cafe_url: str, max_members: int, as_json: bool):
    result = agent.cafe_neighbors(cafe_url, per_page=max_members)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    items = result.get("items", [])
    total = result.get("total_count", len(items))
    print(f"이웃 멤버 (전체 {total:,}명 중 {len(items)}명):")
    for i, m in enumerate(items, 1):
        print(
            f"  {i:3}. {m['nickname']:20} {m.get('grade', ''):10} "
            f"가입:{m.get('join_date', '')}  글:{m.get('article_count', 0):>4}  "
            f"방문:{m.get('visit_count', 0):>5}"
        )


_ALL_COMMANDS = [
    "info",
    "boards",
    "posts",
    "popular",
    "search",
    "article",
    "mycafes",
    "attendance",
    "greetings",
    "levelup",
    "members",
    "profile",
    "photos",
    "liked",
    "scrapped",
    "album",
    "polls",
    "calendar",
    "neighbors",
]


def _run_mycafes(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    cmd_mycafes(agent, args.as_json)


def _run_info(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("info 명령에는 카페 URL이 필요합니다")
    cmd_info(agent, args.cafe_url, args.as_json)


def _run_boards(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("boards 명령에는 카페 URL이 필요합니다")
    cmd_boards(agent, args.cafe_url, args.as_json)


def _run_posts(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("posts 명령에는 카페 URL이 필요합니다")
    cmd_posts(agent, args)


def _run_popular(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("popular 명령에는 카페 URL이 필요합니다")
    cmd_popular(agent, args.cafe_url, max_posts=args.max, as_json=args.as_json)


def _run_search(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url or not args.query:
        parser.error("search 명령에는 카페 URL과 검색어가 필요합니다")
    cmd_search(agent, args.cafe_url, args.query, page=args.page, max_posts=args.max, as_json=args.as_json)


def _run_article(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("article 명령에는 게시글 URL이 필요합니다")
    cmd_article(agent, args.cafe_url, args.as_json)


def _run_attendance(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("attendance 명령에는 카페 URL이 필요합니다")
    cmd_attendance(agent, args.cafe_url, args.as_json)


def _run_greetings(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("greetings 명령에는 카페 URL이 필요합니다")
    cmd_greetings(agent, args.cafe_url, max_posts=args.max, as_json=args.as_json)


def _run_levelup(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("levelup 명령에는 카페 URL이 필요합니다")
    cmd_levelup(agent, args.cafe_url, args.as_json)


def _run_members(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("members 명령에는 카페 URL이 필요합니다")
    cmd_members(agent, args.cafe_url, max_members=args.max, as_json=args.as_json)


def _run_profile(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("profile 명령에는 멤버 URL이 필요합니다")
    cmd_profile(agent, args.cafe_url, args.as_json)


def _run_photos(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("photos 명령에는 카페 URL이 필요합니다")
    cmd_photos(agent, args.cafe_url, board=args.board, max_posts=args.max, as_json=args.as_json)


def _run_liked(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("liked 명령에는 카페 URL이 필요합니다")
    cmd_liked(agent, args.cafe_url, max_posts=args.max, as_json=args.as_json)


def _run_scrapped(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("scrapped 명령에는 카페 URL이 필요합니다")
    cmd_scrapped(agent, args.cafe_url, max_posts=args.max, as_json=args.as_json)


def _run_album(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("album 명령에는 카페 URL이 필요합니다")
    cmd_album(agent, args.cafe_url, menu_id=args.menu_id, page=args.page, max_posts=args.max, as_json=args.as_json)


def _run_polls(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("polls 명령에는 카페 URL이 필요합니다")
    cmd_polls(agent, args.cafe_url, page=args.page, max_polls=args.max, as_json=args.as_json)


def _run_calendar(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("calendar 명령에는 카페 URL이 필요합니다")
    cmd_calendar(agent, args.cafe_url, year=args.year, month=args.month, as_json=args.as_json)


def _run_neighbors(agent: BrowserAgent, parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.cafe_url:
        parser.error("neighbors 명령에는 카페 URL이 필요합니다")
    cmd_neighbors(agent, args.cafe_url, max_members=args.max, as_json=args.as_json)


# cmd 문자열 → 실행 함수. 원래 main() 의 if/elif cmd == ... 순서를 그대로 옮긴 것 — 동작은 동일하다.
# (2026-09-29 STD-08: if/elif 19개가 mccabe/pylint 에 "분기 19개"로 그대로 잡혀 dict 조회로 바꿨다.)
_RUNNERS: dict[str, Callable[[BrowserAgent, argparse.ArgumentParser, argparse.Namespace], None]] = {
    "mycafes": _run_mycafes,
    "info": _run_info,
    "boards": _run_boards,
    "posts": _run_posts,
    "popular": _run_popular,
    "search": _run_search,
    "article": _run_article,
    "attendance": _run_attendance,
    "greetings": _run_greetings,
    "levelup": _run_levelup,
    "members": _run_members,
    "profile": _run_profile,
    "photos": _run_photos,
    "liked": _run_liked,
    "scrapped": _run_scrapped,
    "album": _run_album,
    "polls": _run_polls,
    "calendar": _run_calendar,
    "neighbors": _run_neighbors,
}


def main():
    parser = argparse.ArgumentParser(
        description="네이버 카페 탐색 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command", choices=_ALL_COMMANDS, help="실행할 명령")
    parser.add_argument(
        "cafe_url", nargs="?", default="", help="카페 URL (profile 명령 시 멤버 URL, article 명령 시 게시글 URL)"
    )
    parser.add_argument("query", nargs="?", default="", help="검색어 (search 명령 전용)")
    parser.add_argument("--board", default="", help="게시판명 (기본: 전체글보기)")
    parser.add_argument("--page", type=int, default=1, help="페이지 번호 (기본: 1)")
    parser.add_argument("--pages", type=int, default=1, help="수집할 최대 페이지 수 (기본: 1)")
    parser.add_argument("--max", type=int, default=30, help="최대 수집 수 (기본: 30)")
    parser.add_argument("--year", type=int, default=0, help="캘린더 연도 (기본: 현재 연도)")
    parser.add_argument("--month", type=int, default=0, help="캘린더 월 (기본: 현재 월)")
    parser.add_argument("--menu-id", default="", help="게시판 menuid (album 명령 전용)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON 형식으로 출력")

    args = parser.parse_args()

    from scripts.browser.agent.agent import BrowserAgent

    with BrowserAgent() as agent:
        _RUNNERS[args.command](agent, parser, args)


if __name__ == "__main__":
    main()
