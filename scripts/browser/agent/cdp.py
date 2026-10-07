"""사용자 Chrome CDP 연결 모듈.

목적
====
사용자가 평소 쓰는 Chrome (북마크, 비밀번호 관리자, 로그인 세션 그대로)에
Playwright `connect_over_cdp`로 연결하여 AI가 새 탭으로만 작업.

원칙
====
1. AI는 비밀번호를 모르고 절대 입력하지 않는다.
2. Chrome이 가진 세션 쿠키 / 비밀번호 관리자가 자동 로그인 처리.
3. 사용자 기존 탭은 건드리지 않는다 (AI는 새 탭만 사용).
4. AI 작업이 끝나도 Chrome은 안 닫는다 (탭만 닫음).
5. 은행/구글 등 자동화 차단 사이트도 사용자 Chrome 그대로라 정상 작동.

선행 조건
========
사용자가 Chrome을 디버깅 포트로 시작해야 한다:

    chrome.exe --remote-debugging-port=9222 \
               --user-data-dir="C:\\Users\\<user>\\AppData\\Local\\Google\\Chrome\\User Data"

(또는 helper 스크립트: scripts/browser/cdp/start_chrome_with_cdp.py)

사용 예
======
    from scripts.browser.agent.cdp import open_cdp_session

    with open_cdp_session() as session:
        page = session.new_tab("https://developer.hancom.com")
        # ... 작업
        # 컨텍스트 종료 시: AI가 연 탭만 닫고 Chrome은 유지
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any

DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_HOST = "localhost"
DEFAULT_CONNECT_TIMEOUT_S = 5


class CDPConnectionError(RuntimeError):
    """CDP 연결 실패."""


def cdp_endpoint(host: str = DEFAULT_CDP_HOST, port: int = DEFAULT_CDP_PORT) -> str:
    return f"http://{host}:{port}"


def is_cdp_available(
    host: str = DEFAULT_CDP_HOST,
    port: int = DEFAULT_CDP_PORT,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """CDP 포트가 응답하는지 확인. 결과 dict 반환 (예외 없음)."""
    url = f"{cdp_endpoint(host, port)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:  # noqa: S310
            data = json.loads(res.read().decode("utf-8"))
        return {
            "available": True,
            "host": host,
            "port": port,
            "browser": data.get("Browser", "?"),
            "user_agent": data.get("User-Agent", "?")[:200],
            "webkit_version": data.get("WebKit-Version", "?"),
        }
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return {
            "available": False,
            "host": host,
            "port": port,
            "error": str(e)[:200],
        }


def _default_chrome_path() -> str:
    """Windows 의 기본 Chrome 실행 파일 경로(ProgramFiles 환경변수 기준 — 경로를 코드에 박지 않는다). 값은 이전 기본값과 같다."""
    program_files = os.environ.get("ProgramFiles") or (os.environ.get("SystemDrive", "C:") + r"\Program Files")
    return program_files + r"\Google\Chrome\Application\chrome.exe"


def get_chrome_start_command(
    chrome_path: str | None = None,
    user_data_dir: str | None = None,
    port: int = DEFAULT_CDP_PORT,
) -> str:
    """사용자에게 안내할 Chrome 디버깅 모드 시작 명령어 반환."""
    chrome_path = chrome_path or _default_chrome_path()
    udd = user_data_dir or r"%LOCALAPPDATA%\Google\Chrome\User Data"
    return f'"{chrome_path}" --remote-debugging-port={port} --remote-allow-origins=* --user-data-dir="{udd}"'


@dataclass
class CDPSession:
    """CDP 연결 세션. AI가 연 탭(page) 추적."""

    playwright: Any
    browser: Any
    context: Any
    opened_pages: list = field(default_factory=list)

    def new_tab(self, url: str | None = None, *, wait_until: str = "domcontentloaded", timeout_ms: int = 30000) -> Any:
        """AI 작업용 새 탭 열기. 종료 시 이 탭만 닫는다."""
        page = self.context.new_page()
        self.opened_pages.append(page)
        if url:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        return page

    def close_opened_tabs(self) -> int:
        """AI가 연 탭만 닫고 사용자 기존 탭은 유지. 닫은 개수 반환."""
        closed = 0
        for page in self.opened_pages:
            try:
                if not page.is_closed():
                    page.close()
                    closed += 1
            except Exception:  # noqa: S110, BLE001
                pass
        self.opened_pages.clear()
        return closed

    def list_existing_pages(self) -> list[dict[str, str]]:
        """현재 Chrome의 모든 탭 정보 (URL/title) 반환. 사용자 기존 탭 포함."""
        result = []
        for p in self.context.pages:
            with suppress(Exception):
                result.append({"url": p.url, "title": p.title()})
        return result


@contextmanager
def open_cdp_session(
    host: str = DEFAULT_CDP_HOST,
    port: int = DEFAULT_CDP_PORT,
    *,
    require_existing_chrome: bool = True,
) -> Iterator[CDPSession]:
    """사용자 Chrome에 CDP 연결.

    매개변수
    -------
    host, port : CDP 엔드포인트
    require_existing_chrome : True면 Chrome이 디버깅 모드로 실행 중이지 않을 때
        명확한 안내 메시지와 함께 CDPConnectionError 발생.

    예외
    ----
    CDPConnectionError : Chrome 디버깅 포트 미응답.
    RuntimeError       : playwright 미설치.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright 미설치. `pip install playwright`") from e

    if require_existing_chrome:
        check = is_cdp_available(host, port)
        if not check["available"]:
            cmd = get_chrome_start_command(port=port)
            raise CDPConnectionError(
                f"Chrome 디버깅 포트({host}:{port})가 응답하지 않습니다.\n"
                f"먼저 Chrome을 디버깅 모드로 시작해 주세요:\n  {cmd}\n"
                f"helper: python scripts/browser/cdp/start_chrome_with_cdp.py"
            )

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(cdp_endpoint(host, port))
        # 기존 컨텍스트(사용자 프로필) 사용 — 새 컨텍스트 만들지 않음
        if not browser.contexts:
            raise CDPConnectionError("Chrome에 활성 컨텍스트가 없습니다.")
        context = browser.contexts[0]

        session = CDPSession(playwright=pw, browser=browser, context=context)
        try:
            yield session
        finally:
            # AI가 연 탭만 닫고 Chrome 자체는 유지
            session.close_opened_tabs()
            with suppress(Exception):
                browser.close()  # CDP 연결만 끊음, Chrome 종료 X
    finally:
        with suppress(Exception):
            pw.stop()
