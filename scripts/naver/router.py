"""네이버 서비스 라우터 — 책임별 leaf 모듈 aggregator.

각 서비스 핸들러는 leaf 에 구현돼 있다. run_naver 는 공개 진입점.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from scripts.gate import check as gate_check

from . import blog
from .router_blog import _cmd_blog_assets
from .router_cafe import _cmd_cafe, _cmd_calendar, _cmd_mybox
from .router_common import (  # noqa: F401
    _flag,
    _gate_blog,
    _gate_mail,
    _int_option,
    _option_phrase,
    _option_value,
    _parse_datetime_arg,
    _print_saved,
    _save_latest,
)
from .router_content import (
    _cmd_content,
    _cmd_developers,
    _cmd_excel,
    _cmd_keyword_tools,
    _cmd_seo,
    _cmd_shopping,
)
from .router_social import _cmd_pay, _cmd_place, _cmd_smartstore, _cmd_talk
from .router_system import _cmd_catalog, _cmd_login, _cmd_session_check

__status__ = {
    "tasks": {
        "blog write": "done",
        "blog publish": "done",
        # 2026-09-29 정정(defect_index #38): 이 CLI 라우터의 "mail" 분기는 mail.run()
        # 을 호출하는데 그 함수 자체가 존재한 적이 없음(scripts/naver/mail/ 은 발송/답장을
        # 모듈 차원에서 금지하는 읽기전용 패키지로 재구성됨). 실제 메일 조회/조작은
        # ai_orchestrator/connectors/naver_mail_router.py(API)로만 가능.
        "mail inbox": "not_implemented_cli",
        "mail compose": "not_implemented",
        "mail send": "not_implemented",
        "content explore": "done",
        "content actions": "done",
        "company seo": "done",
        "developers entrypoints": "done",
        "shopping competitors": "done",
        "keyword tools": "done",
        "excel report": "done",
        "cafe list": "done",
        "cafe write": "done",
        "calendar list/add": "done",
        "mybox list/search/upload": "done",
        "pay orders/points": "done",
        "talk list/send": "done",
        "place list/reviews": "done",
        "smartstore alias": "done",
        "service catalog": "done",
        "login": "done",
        "session-check": "done",
    },
    "note": "블로그 글쓰기·발행 완성. 메일은 API 라우터(naver_mail_router.py)만 구현됨 —"
    " 이 CLI 라우터의 mail 분기는 미구현(2026-09-29 정정).",
}


def run_naver(task: str, sub: str, args: list[str]) -> None:
    """네이버 서비스 라우팅.

    task: blog | mail | session-check | login
    sub: write / inbox / compose 등 하위 명령
    """
    match task:
        case "blog":
            if "--dry-run" not in [str(a) for a in args]:
                _gate_blog(sub)
            blog.run(sub or "write", args)
        case "mail":
            _gate_mail(sub)
            # scripts.naver.mail 은 설계상 발송/답장/삭제 등을 모듈 차원에서 금지하는
            # 읽기전용 패키지로 재구성됐고(패키지 __init__.py 문서화) run() 진입점 자체가
            # 없음 — 아래 __status__ 의 "mail inbox/compose/send: done" 주장과 실제 상태가
            # 어긋나 있었음(2026-09-29 defect_index #38, notification_hub.py/#37 과 동일
            # 근본원인). CLI 로 메일 조회가 필요하면 scripts/naver/mail/collection/
            # inbox_collector.py 등을 직접 쓰거나 별도 기준서로 run() 진입점을 새로 설계할 것.
            print(
                "[mail] CLI 진입점(run())이 아직 구현되지 않았습니다 — scripts/naver/mail/ 은 API 라우터(naver_mail_router.py)로만 접근 가능합니다."
            )
        case _:
            _run_naver_content_task(task, sub, args)


def _run_naver_content_task(task: str, sub: str, args: list[str]) -> None:
    """run_naver 의 중간 단계 라우팅(blog-assets/content/seo/developers/shopping/keyword-tools/excel)."""
    match task:
        case "blog-assets" | "blog-media":
            _cmd_blog_assets(sub or "plan", args)
        case "content":
            _cmd_content(sub or "explore", args)
        case "seo":
            _cmd_seo(sub or "plan", args)
        case "developers":
            _cmd_developers(sub or "entrypoints", args)
        case "shopping":
            _cmd_shopping(sub or "competitors", args)
        case "keyword-tools" | "keywords" | "keyword":
            _cmd_keyword_tools(sub or "catalog", args)
        case "excel" | "report":
            _cmd_excel(sub or "report", args)
        case _:
            _run_naver_service_task(task, sub, args)


def _run_naver_service_task(task: str, sub: str, args: list[str]) -> None:
    """run_naver 의 나머지 서비스 라우팅(cafe/calendar/mybox/pay/talk/place/smartstore/...)."""
    match task:
        case "cafe":
            _cmd_cafe(sub or "list", args)
        case "calendar":
            _cmd_calendar(sub or "list", args)
        case "mybox":
            _cmd_mybox(sub or "list", args)
        case "pay":
            _cmd_pay(sub or "orders", args)
        case "talk":
            _cmd_talk(sub or "list", args)
        case "place":
            _cmd_place(sub or "list", args)
        case "smartstore":
            _cmd_smartstore(sub or "actions", args)
        case _:
            _run_naver_system_task(task)


def _run_naver_system_task(task: str) -> None:
    """run_naver 의 마지막 단계 라우팅(catalog/session-check/login)."""
    match task:
        case "catalog" | "actions" | "index":
            _cmd_catalog()
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
