"""카카오 서비스 공통 — 로그인 확인, 작업 컨텍스트"""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.browser.page.page_helper import (  # noqa: E402
    page_goto,
    page_wait_click,
    page_wait_type,
    page_wait_visible,
)
from scripts.browser.page.web_connector import browser_session  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.site_engine.login_session import ensure_login, is_logged_in  # noqa: E402

log = get_logger(__name__)

KAKAO_DEV_URL = "https://developers.kakao.com/console/app"

__all__ = [
    "check_session",
    "page_goto",
    "page_wait_click",
    "page_wait_type",
    "page_wait_visible",
    "task_context",
]


def check_session() -> dict:
    """데몬 Chrome에서 카카오 로그인 상태 실시간 확인."""
    result: dict[str, Any] = {"logged_in": None, "error": None}
    try:
        with browser_session() as page:
            result["logged_in"] = is_logged_in(page, "kakao")
    except Exception as e:  # noqa: BLE001 - 카카오 서비스 로그인 상태 확인(check_session, 읽기전용) - 실패 시 error 필드만 채우고 logged_in은 None(미확인) 유지, 세션 파기나 자격증명 노출 없음
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
