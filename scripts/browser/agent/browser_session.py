"""사용자 브라우저 세션 관리 모듈.

목적
====
사용자가 자연어로 브라우저 탐색을 요청할 때, 매번 새 Playwright 브라우저를
launch 하지 않고 **사용자 로그인 세션을 유지**한 채 같은 브라우저를 재사용.

원칙
====
1. 1회 로그인 → 이후 자동 로그인 (persistent context)
2. 사용자에게 보이는 창 (headless=False 기본)
3. 실제 Chrome 채널 사용 (compatibility 최대)
4. 프로필별 독립 세션 (사이트별 격리 가능)
5. 보안 정책 준수: 자격증명 자동 입력 금지, 캡처 정책 유지

사용 예
======
    from scripts.browser.agent.session import open_user_session

    with open_user_session(profile_name="hancom_dev") as session:
        page = session.new_page()
        page.goto("https://developer.hancom.com/")
        # 처음에는 로그인 화면 → 사용자가 직접 로그인
        # 이후 호출에서는 자동 로그인 상태로 시작
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from ai_orchestrator.paths import repo_root

# 이동해도 값이 안 바뀌게 __file__ 상대 계산 대신 repo_root() 기준으로 고정(T4 C1).
# 지금 값과 완전히 동일(ai_orchestrator/data/browser_sessions).
_DEFAULT_SESSION_ROOT = repo_root() / "ai_orchestrator" / "data" / "browser_sessions"


def get_session_dir(profile_name: str = "default") -> Path:
    """프로필별 세션 디렉터리 경로 반환 (없으면 생성)."""
    if not profile_name or "/" in profile_name or "\\" in profile_name or ".." in profile_name:
        raise ValueError(f"profile_name 형식 오류: {profile_name!r}")
    session_dir = _DEFAULT_SESSION_ROOT / profile_name
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def list_profiles() -> list[str]:
    """저장된 프로필 목록 반환."""
    if not _DEFAULT_SESSION_ROOT.exists():
        return []
    return sorted(p.name for p in _DEFAULT_SESSION_ROOT.iterdir() if p.is_dir())


@contextmanager
def open_user_session(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    profile_name: str = "default",
    *,
    headless: bool = False,
    channel: str = "chrome",
    start_url: str | None = None,
    maximized: bool = True,
    extra_args: tuple[str, ...] = (),
    save_storage: bool = True,
) -> Iterator[Any]:
    """사용자 세션 브라우저 열기 (persistent context + 자동 storage_state 저장).

    매개변수
    -------
    profile_name : 세션 식별자 (사이트별로 분리 권장: "hancom_dev", "g2b" 등)
    headless     : 기본 False — 사용자가 로그인 등 직접 개입 가능해야 함
    channel      : 'chrome' 권장 (chromium, msedge 가능)
    start_url    : 열자마자 이동할 URL (None이면 about:blank)
    maximized    : 창 최대화 여부
    extra_args   : 추가 Chromium 인자
    save_storage : 기본 True — 종료 시 쿠키/세션을 storage_state.json에 저장

    반환
    ----
    BrowserContext (Playwright persistent context)

    주의
    ----
    - 첫 호출 시 로그인 필요 → 사용자가 창에서 직접 로그인
    - 두 번째 호출부터는 자동 로그인 상태 (저장된 쿠키/세션 복원)
    - 자격증명 자동 입력 금지 (보안 정책)
    - storage_state는 data/browser_sessions/{profile_name}/state.json에 저장됨
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("playwright 미설치. `pip install playwright` 후 `playwright install chrome` 실행.") from e

    session_dir = get_session_dir(profile_name)
    storage_state_path = session_dir / "state.json"

    args = list(extra_args)
    if maximized and not any(a.startswith("--start-maximized") for a in args):
        args.append("--start-maximized")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=headless,
            channel=channel if channel else None,
            args=args,
            ignore_default_args=["--enable-automation"],
            no_viewport=True if maximized else False,
        )
        # 자동화 감지 우회 — 모든 페이지에 적용
        context.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        try:
            if start_url:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(start_url, timeout=60000, wait_until="domcontentloaded")
            yield context
        finally:
            # 브라우저 종료 시 storage_state 저장
            if save_storage:
                try:
                    context.storage_state(path=str(storage_state_path))
                except Exception as e:  # noqa: BLE001 - 사용자 브라우저 영속 세션 관리 — storage_state 저장 실패는 경고 출력만(세션이 저장되지 않을 뿐 데이터 유출 아님), context.close 실패는 무시, is_likely_logged_in은 예외 시 False(=로그인 안 됨, 보수적 방향)로 폴백해 미인증 상태로 안전하게 처리됨.
                    print(f"[경고] storage_state 저장 실패: {e}")
            with suppress(Exception):
                context.close()


def wait_for_user_action(seconds: int = 60, message: str = "") -> None:
    """사용자가 브라우저에서 작업할 시간을 기다린다 (블로킹 sleep)."""
    if message:
        print(f"[user_browser_session] {message} ({seconds}초 대기)")
    time.sleep(seconds)


def is_likely_logged_in(page: Any, login_keywords: tuple[str, ...] = ("로그인", "Sign in", "Log in")) -> bool:
    """페이지에 '로그인' 단어가 보이지 않으면 로그인된 것으로 추정.

    완벽하지 않은 휴리스틱 — 사이트별로 정확한 셀렉터를 쓰는 것을 권장.
    """
    try:
        body = page.inner_text("body")[:5000]
        return not any(kw in body for kw in login_keywords)
    except Exception:  # noqa: BLE001 - 사용자 브라우저 영속 세션 관리 — storage_state 저장 실패는 경고 출력만(세션이 저장되지 않을 뿐 데이터 유출 아님), context.close 실패는 무시, is_likely_logged_in은 예외 시 False(=로그인 안 됨, 보수적 방향)로 폴백해 미인증 상태로 안전하게 처리됨.
        return False
