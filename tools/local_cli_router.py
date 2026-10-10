"""로컬 에이전트 서비스 라우터 — 고위험 정부/민원 자동화."""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.common.logger import get_logger

__status__ = {
    "tasks": {
        "gov24 (주민등록등본)": "partial",
        "minwon (민원24)": "partial",
        "blog-explore": "done",
        "blog-scrape": "done",
        "check (playwright)": "done",
        "create-profile": "partial",
    },
    "note": "gov24/minwon = 승인(APPROVE) 필수 고위험. 개인정보 관련 작업",
}

_log = get_logger(__name__)


def run_local_agent(task: str | None, sub: str | None, args: list[str]) -> None:
    """로컬 에이전트 서비스 라우팅.

    task: gov24 | minwon | blog-explore | blog-scrape | check | create-profile
    """
    match task or "help":
        case "gov24":
            _cmd_gov24(sub, args)
        case "minwon":
            _cmd_minwon(sub, args)
        case "blog-explore":
            _cmd_blog_explore(args)
        case "blog-scrape":
            _cmd_blog_scrape(args)
        case "check":
            _cmd_check()
        case "create-profile":
            _cmd_create_profile(args)
        case _:
            _print_help()


def _cmd_gov24(sub: str | None, args: list[str]) -> None:
    # 주민등록등본 발급 = 개인정보 관련 고위험
    gate_check("eum_register", force=False)  # APPROVE 등급
    print("[로컬에이전트] 정부24 주민등록등본 발급")
    from scripts.site_engine.gov24_certificate import main

    main()


def _cmd_minwon(sub: str | None, args: list[str]) -> None:
    gate_check("eum_register", force=False)  # APPROVE 등급
    print("[로컬에이전트] 민원24 온라인 민원 접수")
    from scripts.site_engine.minwon_submit import main

    main()


def _cmd_blog_explore(args: list[str]) -> None:
    gate_check("goto")
    blog_id = args[0] if args else ""
    print(f"[로컬에이전트] 네이버 블로그 탐색: {blog_id or '(ID 미지정)'}")
    from scripts.naver.blog.community.blog_explorer import main

    main()


def _cmd_blog_scrape(args: list[str]) -> None:
    gate_check("goto")
    blog_id = args[0] if args else ""
    print(f"[로컬에이전트] 네이버 블로그 수집: {blog_id or '(ID 미지정)'}")
    from scripts.naver.blog.utilities.blog_scraper import main

    main()


def _cmd_check() -> None:
    gate_check("goto")
    print("[로컬에이전트] Playwright 환경 점검")
    from tools.verify.check_playwright_bootstrap import main

    main()


def _cmd_create_profile(args: list[str]) -> None:
    gate_check("goto")
    site = args[0] if args else ""
    print(f"[로컬에이전트] 사이트 프로파일 생성: {site or '(URL 미지정)'}")
    from scripts.site_engine.create_site_profile import main

    main()


def _print_help() -> None:
    print("""로컬에이전트 사용법:
  python scripts/entry/cdp_cli.py local gov24           정부24 주민등록등본 발급 (승인 필요)
  python scripts/entry/cdp_cli.py local minwon          민원24 온라인 민원 접수 (승인 필요)
  python scripts/entry/cdp_cli.py local blog-explore <ID>  네이버 블로그 탐색
  python scripts/entry/cdp_cli.py local blog-scrape <ID>   네이버 블로그 수집
  python scripts/entry/cdp_cli.py local check           Playwright 환경 점검
  python scripts/entry/cdp_cli.py local create-profile <URL> 사이트 프로파일 생성""")
