"""카페 CLI 러너 — 글쓰기 / 수집 / 분석 / 탐색.

사용:
    # 내 가입 카페 목록
    python -m scripts.naver.cafe._runner my-cafes

    # 카페 구조 탐색
    python -m scripts.naver.cafe._runner explore --cafe-url=https://cafe.naver.com/0moo

    # 글쓰기
    python -m scripts.naver.cafe._runner write \\
        --cafe-url=https://cafe.naver.com/0moo \\
        --board="건설 공무 관련 업무" --title=제목 --body=본문

    python -m scripts.naver.cafe._runner confirm

    # 3개월치 수집
    python -m scripts.naver.cafe._runner collect \\
        --cafe-url=https://cafe.naver.com/0moo \\
        --days=90 --max-detail=300

    # 수집 → 분류 → 군집화 전체 파이프라인
    python -m scripts.naver.cafe._runner collect-pipeline \\
        --cafe-url=https://cafe.naver.com/0moo --days=90

    # 분석 (수집 파일 자동 탐색)
    python -m scripts.naver.cafe._runner analyze

    # 수집 + 분석 한 번에
    python -m scripts.naver.cafe._runner collect-analyze \\
        --cafe-url=https://cafe.naver.com/0moo
"""
from __future__ import annotations

import argparse
import json
import sys

from scripts.browser.cdp.connection import get_page
from .writer import write_post, confirm_publish


def _task_my_cafes(args: argparse.Namespace) -> dict:
    from .explorer import get_my_cafes, save_my_cafes
    page = get_page()
    cafes = get_my_cafes(page)
    path = save_my_cafes(cafes)
    for i, c in enumerate(cafes, 1):
        print(f"  {i:2}. {c['cafe_id']:20} | {c['cafe_name'][:35]}")
    return {"ok": True, "count": len(cafes), "saved": path}


def _task_explore(args: argparse.Namespace) -> dict:
    from .explorer import explore_cafe
    page = get_page()
    info = explore_cafe(page, args.cafe_url)
    print(f"카페명: {info['cafe_name']}")
    print(f"clubid: {info['clubid']}")
    print(f"회원수: {info['member_count']:,}")
    print(f"소개: {info.get('description','')[:80]}")
    print(f"게시판 {len(info['boards'])}개:")
    for b in info['boards'][:20]:
        print(f"  [{b['menu_id']}] {b['name']}")
    return info


def _task_collect_pipeline(args: argparse.Namespace) -> dict:
    from .collector import collect_articles
    from .pipeline import run_pipeline
    from .organizer import organize
    page = get_page()
    articles = collect_articles(
        page,
        cafe_url=args.cafe_url,
        days=args.days,
        max_detail=args.max_detail,
    )
    print(f"[pipeline] 수집 완료: {len(articles)}건")
    pipe_result = run_pipeline()
    org_result = organize()
    print(org_result["report_text"])
    return {
        "ok": True,
        "collected": len(articles),
        "pipeline_stats": pipe_result["stats"],
        "report": org_result["txt_path"],
    }


def _task_write(args: argparse.Namespace) -> dict:
    page = get_page()
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    return write_post(
        page,
        cafe_url=args.cafe_url,
        board_name=args.board,
        title=args.title,
        body=args.body,
        tags=tags or None,
        members_only=args.members_only,
        require_approval=not args.publish,
    )


def _task_confirm(args: argparse.Namespace) -> dict:
    page = get_page()
    return confirm_publish(page)


def _task_collect(args: argparse.Namespace) -> dict:
    from .collector import collect_articles
    page = get_page()
    articles = collect_articles(
        page,
        cafe_url=args.cafe_url,
        days=args.days,
        max_detail=args.max_detail,
    )
    return {"ok": True, "count": len(articles)}


def _task_analyze(args: argparse.Namespace) -> dict:
    from .analyzer import load_latest, analyze, save_report
    raw = load_latest(getattr(args, "data_dir", None))
    report = analyze(raw)
    print(report["summary_text"])
    paths = save_report(report)
    return {"ok": True, "files": paths, "total": report["total"]}


def _task_collect_analyze(args: argparse.Namespace) -> dict:
    from .collector import collect_articles
    from .analyzer import analyze, save_report
    page = get_page()
    articles = collect_articles(
        page,
        cafe_url=args.cafe_url,
        days=args.days,
        max_detail=args.max_detail,
    )
    report = analyze(articles)
    print(report["summary_text"])
    paths = save_report(report)
    return {"ok": True, "collected": len(articles), "files": paths}


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cafe_runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # write
    wp = sub.add_parser("write")
    wp.add_argument("--cafe-url", required=True)
    wp.add_argument("--board", default="")
    wp.add_argument("--title", required=True)
    wp.add_argument("--body", required=True)
    wp.add_argument("--tags", default="")
    wp.add_argument("--members-only", action="store_true")
    wp.add_argument("--publish", action="store_true", help="승인 게이트 없이 즉시 발행")

    # confirm
    sub.add_parser("confirm")

    # collect
    cp = sub.add_parser("collect")
    cp.add_argument("--cafe-url", default="https://cafe.naver.com/0moo")
    cp.add_argument("--days", type=int, default=90)
    cp.add_argument("--max-detail", type=int, default=300, dest="max_detail")

    # analyze
    ap = sub.add_parser("analyze")
    ap.add_argument("--data-dir", default=None, dest="data_dir")

    # collect-analyze (one-shot)
    cap = sub.add_parser("collect-analyze")
    cap.add_argument("--cafe-url", default="https://cafe.naver.com/0moo")
    cap.add_argument("--days", type=int, default=90)
    cap.add_argument("--max-detail", type=int, default=300, dest="max_detail")

    # my-cafes
    sub.add_parser("my-cafes")

    # explore
    ep = sub.add_parser("explore")
    ep.add_argument("--cafe-url", required=True)

    # collect-pipeline
    cpp = sub.add_parser("collect-pipeline")
    cpp.add_argument("--cafe-url", default="https://cafe.naver.com/0moo")
    cpp.add_argument("--days", type=int, default=90)
    cpp.add_argument("--max-detail", type=int, default=300, dest="max_detail")

    args = parser.parse_args(argv)

    if args.cmd == "my-cafes":
        result = _task_my_cafes(args)
    elif args.cmd == "explore":
        result = _task_explore(args)
    elif args.cmd == "collect-pipeline":
        result = _task_collect_pipeline(args)
    elif args.cmd == "write":
        result = _task_write(args)
    elif args.cmd == "confirm":
        result = _task_confirm(args)
    elif args.cmd == "collect":
        result = _task_collect(args)
    elif args.cmd == "analyze":
        result = _task_analyze(args)
    elif args.cmd == "collect-analyze":
        result = _task_collect_analyze(args)
    else:
        print("알 수 없는 명령", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
