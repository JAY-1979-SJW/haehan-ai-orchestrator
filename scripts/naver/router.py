"""네이버 서비스 라우터 — 책임별 leaf 모듈 aggregator.

각 서비스 핸들러는 leaf 에 구현돼 있다. run_naver 는 공개 진입점.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

from scripts.common.gate import check as gate_check  # noqa: F401 — tests patch router.gate_check
from scripts.naver.blog.cli_router import _cmd_blog_assets  # noqa: F401
from scripts.naver.cafe.cli_router import _cmd_cafe, _cmd_calendar, _cmd_mybox  # noqa: F401

from . import blog
from .dispatch import _run_naver_content_task, _run_naver_service_task, _run_naver_system_task  # noqa: F401
from scripts.naver.common.router_common import _flag, _gate_blog, _gate_mail, _int_option, _option_phrase, _option_value, _parse_datetime_arg, _print_saved, _save_latest  # noqa: F401
from .router_content import (  # noqa: F401
    _cmd_content,
    _cmd_developers,
    _cmd_excel,
    _cmd_keyword_tools,
    _cmd_seo,
    _cmd_shopping,
)
from .router_social import _cmd_pay, _cmd_place, _cmd_smartstore, _cmd_talk  # noqa: F401
from .router_status import __status__  # noqa: F401
from .router_system import _cmd_catalog, _cmd_login, _cmd_session_check  # noqa: F401


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
