"""네이버 서비스 라우터 — 책임별 leaf 모듈 aggregator.

각 서비스 핸들러는 leaf 에 구현돼 있다. run_naver 는 공개 진입점.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from . import blog, mail
from scripts.gate import check as gate_check

from .router_common import (  # noqa: F401
    _option_value, _option_phrase, _flag, _int_option,
    _save_latest, _print_saved, _parse_datetime_arg,
    _gate_blog, _gate_mail,
)
from .router_blog import _cmd_blog_assets  # noqa: F401
from .router_content import (  # noqa: F401
    _cmd_content, _cmd_seo, _cmd_developers, _cmd_shopping, _cmd_excel, _cmd_keyword_tools,
)
from .router_cafe import _cmd_cafe, _cmd_calendar, _cmd_mybox  # noqa: F401
from .router_social import _cmd_pay, _cmd_talk, _cmd_place, _cmd_smartstore  # noqa: F401
from .router_system import _cmd_catalog, _cmd_session_check, _cmd_login  # noqa: F401

__status__ = {
    "tasks": {
        "blog write": "done", "blog publish": "done",
        "mail inbox": "done", "mail compose": "done", "mail send": "done",
        "content explore": "done", "content actions": "done",
        "company seo": "done", "developers entrypoints": "done",
        "shopping competitors": "done", "keyword tools": "done",
        "excel report": "done", "cafe list": "done",
        "calendar list/add": "done", "mybox list/search/upload": "done",
        "pay orders/points": "done", "talk list/send": "done",
        "place list/reviews": "done", "smartstore alias": "done",
        "service catalog": "done", "login": "done", "session-check": "done",
    },
    "note": "블로그 글쓰기·발행, 메일 수신/발송 자동화 완성",
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
            mail.run(sub or "inbox", args)
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
        case "catalog" | "actions" | "index":
            _cmd_catalog()
        case "session-check":
            _cmd_session_check()
        case "login":
            gate_check("wait_login", risk="notify")
            _cmd_login()
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")
