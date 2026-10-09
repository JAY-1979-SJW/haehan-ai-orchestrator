"""사이트 베이스 공통 — 로그인 확인 + 작업 컨텍스트 단일 구현.

google/naver/kakao 등 각 사이트의 base.py에 중복되어 있던
check_session() / task_context() 를 한 곳으로 모은 모듈.

각 사이트 base는 본 모듈에 위임만 한다. 시그니처/동작은 보존.

차이 파라미터:
    use_existing_tab : True 면 CDP 기존 탭 재사용(google),
                       False 면 새 탭 생성 후 종료 시 닫음(naver/kakao)
    start_url        : 컨텍스트 진입 직후 이동할 URL (선택)
    with_db_log      : True 면 cdp_db.log_start/log_finish 기록
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.site_engine.login_session import ensure_login, is_logged_in  # noqa: E402
from scripts.browser.cdp.connection import close_page, get_page  # noqa: E402
from scripts.browser.page.web_connector import browser_session  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

log = get_logger(__name__)


def check_session(site: str) -> dict:
    """데몬 Chrome에서 site의 로그인 상태 실시간 확인."""
    result: dict = {"logged_in": None, "error": None}
    try:
        with browser_session() as page:
            result["logged_in"] = is_logged_in(page, site)
    except Exception as e:  # noqa: BLE001 - check_session은 세션 확인 실패를 error 필드에 기록하고 logged_in을 True로 바꾸지 않는 안전한 기본값(None 유지); task_context의 except는 로그만 남기고 예외를 다시 raise(재전파)해 흡수하지 않음.
        result["error"] = str(e)
    return result


@contextmanager
def task_context(
    site: str,
    task: str,
    args: list[str],
    *,
    start_url: str | None = None,
    use_existing_tab: bool = False,
    with_db_log: bool = False,
) -> Generator[Page]:
    """사이트 작업 실행 컨텍스트 — 로그인 확인 + (선택) DB 로그 기록."""
    log.info("[%s] %s 시작 args=%s", site, task, args)

    log_id = None
    if with_db_log:
        from scripts.browser.cdp.cdp_db import log_start

        log_id = log_start(site, task, args)

    page: Page | None = None
    try:
        if use_existing_tab:
            page = get_page()
        else:
            # browser_session 컨텍스트는 yield 안에서 page 사용 후 자동 close
            with browser_session() as p:
                page = p
                if start_url:
                    page.goto(start_url, timeout=30000)
                ensure_login(page, site)
                yield page
                if with_db_log and log_id is not None:
                    from scripts.browser.cdp.cdp_db import log_finish

                    log_finish(log_id, "success")
                log.info("[%s] %s 완료", site, task)
            return

        # use_existing_tab 경로
        if start_url:
            page.goto(start_url, timeout=30000)
        ensure_login(page, site)
        yield page
        if with_db_log and log_id is not None:
            from scripts.browser.cdp.cdp_db import log_finish

            log_finish(log_id, "success")
        log.info("[%s] %s 완료", site, task)
    except Exception as e:
        if with_db_log and log_id is not None:
            from scripts.browser.cdp.cdp_db import log_finish

            log_finish(log_id, "fail", error_msg=str(e))
        log.error("[%s] %s 실패: %s", site, task, e)
        raise
    finally:
        if use_existing_tab and page is not None:
            close_page(page)
