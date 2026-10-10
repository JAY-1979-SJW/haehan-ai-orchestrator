"""네이버 라우터 중·후단 디스패치 — run_naver 가 위임하는 순수 라우팅.

router.py(컴포지션 루트)와 router_* leaf 사이의 조합 계층이라 leaf 가 아니다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.naver.blog.cli_router import _cmd_blog_assets
from scripts.naver.cafe.cli_router import _cmd_cafe, _cmd_calendar, _cmd_mybox

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
