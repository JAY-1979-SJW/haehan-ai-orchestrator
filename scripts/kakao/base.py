"""카카오 서비스 공통 — 로그인 확인, 작업 컨텍스트"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import browser_session  # noqa: E402
from scripts.login_session import is_logged_in, ensure_login  # noqa: E402
from scripts.logger import get_logger  # noqa: E402
from scripts.page_helper import (  # noqa: E402
    page_goto,
    page_wait_visible,
    page_wait_click,
    page_wait_type,
)

log = get_logger(__name__)

KAKAO_DEV_URL = "https://developers.kakao.com/console/app"

__all__ = [
    "page_goto", "page_wait_visible", "page_wait_click", "page_wait_type",
    "task_context", "check_session",
]


def check_session() -> dict:
    """데몬 Chrome에서 카카오 로그인 상태 실시간 확인."""
    result = {"logged_in": None, "error": None}
    try:
        with browser_session() as page:
            result["logged_in"] = is_logged_in(page, "kakao")
    except Exception as e:
        result["error"] = str(e)
    return result


@contextmanager
def task_context(task: str, args: list[str]) -> Generator:
    """카카오 작업 컨텍스트 — 데몬 Chrome 연결 + 로그인 확인."""
    log.info("[kakao] %s 시작 args=%s", task, args)
    with browser_session() as page:
        ensure_login(page, "kakao")
        yield page
        log.info("[kakao] %s 완료", task)
