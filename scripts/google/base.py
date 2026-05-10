"""Google 서비스 공통 - CDP, 세션, 로그"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SESSION_DIR = ROOT / "data" / "browser_sessions" / "google"


# ── CDP 연결 ────────────────────────────────────────────────────────

def get_page(headless: bool = False) -> Page:
    """CDP 브라우저에 연결해 새 페이지 반환."""
    from scripts.cdp_db import init_db
    init_db()

    # CDPport 읽기
    daemon_state_file = ROOT / "data" / "cdp_daemon_state.json"
    if not daemon_state_file.exists():
        raise RuntimeError("CDP 데몬이 실행 중이지 않습니다. 'python scripts/cdp_daemon.py start' 실행하세요")
    state = json.loads(daemon_state_file.read_text(encoding="utf-8"))
    port = state.get("cdp_port", 9222)

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")

    # 첫 컨텍스트 가져오기 또는 새로 생성
    ctx = None
    for _ in range(10):
        if browser.contexts:
            ctx = browser.contexts[0]
            break
        time.sleep(1)

    if not ctx:
        raise RuntimeError("CDP 브라우저 컨텍스트 생성 실패")

    return ctx.new_page()


def _is_logged_in_google(page: Page) -> bool:
    """Google 로그인 상태 판별."""
    try:
        page.goto("https://www.google.com", timeout=10000, wait_until="domcontentloaded")
        time.sleep(2)
        # 로그인 상태 → 프로필 이미지 등으로 판별 가능
        # 간단히: 현재 URL 기반 판별
        return not ("accounts.google.com" in page.url or "signin" in page.url.lower())
    except Exception:
        return False


def _ensure_login(page: Page) -> None:
    """로그인 확인, 미로그인 시 안내."""
    if _is_logged_in_google(page):
        print("  ✓ Google 로그인됨")
        return

    print("  ✗ Google 로그인이 필요합니다")
    print("  💡 브라우저에서 Google에 로그인하세요")
    print("  ⏳ 최대 5분 대기 중...\n")

    start = time.time()
    while time.time() - start < 300:
        time.sleep(2)
        if _is_logged_in_google(page):
            print("  ✓ 로그인 완료")
            return

    raise RuntimeError("로그인 타임아웃")


@contextmanager
def task_context(site: str, task: str, args: list[str]) -> Generator[Page, None, None]:
    """작업 실행 컨텍스트 - 로그 자동 기록."""
    from scripts.cdp_db import log_start, log_finish

    log_id = log_start(site, task, args)

    try:
        page = get_page()
        _ensure_login(page)
        yield page
        log_finish(log_id, "success")
    except Exception as e:
        log_finish(log_id, "fail", error_msg=str(e))
        raise
    finally:
        try:
            page.close()
        except Exception:
            pass
