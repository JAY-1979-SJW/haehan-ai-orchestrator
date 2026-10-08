"""네이버 서비스 공통 — 로그인 확인, 작업 컨텍스트"""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.browser.page.page_helper import (  # noqa: E402
    page_goto,
    page_wait_click,
    page_wait_nav,
    page_wait_type,
    page_wait_visible,
)
from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)

SESSION_NAME = "naver"

__all__ = [
    "check_session",
    "page_goto",
    "page_wait_click",
    "page_wait_nav",
    "page_wait_type",
    "page_wait_visible",
    "task_context",
]


from scripts.naver.browser_gate import require_naver_browser  # noqa: E402
from scripts.site_engine.site_base import (  # noqa: E402
    check_session as _check_session_base,
)
from scripts.site_engine.site_base import (  # noqa: E402
    task_context as _task_context_base,
)


def check_session() -> dict:
    """데몬 Chrome에서 네이버 로그인 상태 실시간 확인."""
    require_naver_browser()
    return _check_session_base("naver")


@contextmanager
def task_context(task: str, args: list[str]) -> Generator:
    """네이버 작업 컨텍스트 — 데몬 Chrome 연결 + 로그인 확인."""
    require_naver_browser()
    with _task_context_base(
        "naver",
        task,
        args,
        start_url="https://www.naver.com/",
    ) as page:
        yield page
