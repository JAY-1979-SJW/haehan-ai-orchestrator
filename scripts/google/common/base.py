"""Google 서비스 공통 - 로그인 확인, 작업 컨텍스트

브라우저 연결 → scripts.browser.page.web_connector
페이지 헬퍼   → scripts.browser.page.page_helper
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# 브라우저 연결 모듈
from scripts.browser.cdp.connection import get_page as _wc_get_page  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

# 로그인 세션 모듈

# 공통 페이지 헬퍼 re-export
from scripts.browser.page.page_helper import (  # noqa: E402
    page_goto,
    page_wait_click,
    page_wait_nav,
    page_wait_type,
    page_wait_visible,
)

__all__ = [
    "check_session",
    "get_page",
    "page_goto",
    "page_wait_click",
    "page_wait_nav",
    "page_wait_type",
    "page_wait_visible",
    "task_context",
]


from scripts.site_engine.site_base import (  # noqa: E402
    check_session as _check_session_base,
)
from scripts.site_engine.site_base import (  # noqa: E402
    task_context as _task_context_base,
)


def check_session() -> dict:
    """데몬 Chrome에서 Google 로그인 상태 실시간 확인."""
    return _check_session_base("google")


def get_page(headless: bool = False) -> Page:
    """CDP 브라우저의 기존 탭 재사용. (web_connector.get_page 위임)"""
    from scripts.browser.cdp.cdp_db import init_db

    init_db()
    return _wc_get_page()


@contextmanager
def task_context(site: str, task: str, args: list[str]) -> Generator[Page, None, None]:
    """작업 실행 컨텍스트 - 로그인 확인 + DB 로그 자동 기록."""
    from scripts.browser.cdp.cdp_db import init_db

    init_db()
    with _task_context_base(
        site,
        task,
        args,
        use_existing_tab=True,
        with_db_log=True,
    ) as page:
        yield page
