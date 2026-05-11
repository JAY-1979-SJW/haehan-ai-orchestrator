#!/usr/bin/env python3
"""CDP로 Google Cloud Console 접속 → API 활성화 + OAuth credentials 생성.

흐름: 페이지 이동 → 목표 요소 등장 신호 → 즉시 상호작용
     → 네트워크+DOM+폴링 3중 검증 → 다음 단계
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page, close_page
from scripts.page_helper import (
    page_goto_wait,
    page_wait_visible,
    page_wait_click,
    page_wait_type,
    page_click_then_wait,
    page_submit_and_verify,
    page_inspect,
)
from scripts.config import (
    USER_EMAIL, PROJECT_NAME, OAUTH_CLIENT_NAME,
    GOOGLE_URLS, GOOGLE_CLOUD_APIS,
)

CREDENTIALS_FILE = ROOT / "credentials.json"

# ── 셀렉터 상수 ───────────────────────────────────────────────────────
_SEL_PROJECT_NAME = (
    '#p6ntest-name-input, #p-name, '
    'input[id*="name-input"], input[id*="project-name"]'
)
_SEL_CREATE_BTN   = (
    'button:has-text("만들기"), button:has-text("Create"), '
    'a:has-text("만들기"), a:has-text("Create")'
)
_SEL_DASHBOARD    = '[aria-label*="dashboard"], [data-view="dashboard"], .console-header'

# Google Console API 버튼 — Angular Material: <button> 안에 <span>으로 텍스트 감싸짐
# has-text()는 하위 텍스트 포함 매칭이므로 button/a/span 모두 포함
_SEL_API_ENABLE   = (
    'button:has-text("사용"), a:has-text("사용"), span:has-text("사용"), '
    'button:has-text("Enable"), a:has-text("Enable")'
)
_SEL_API_ACTIVE   = (
    'button:has-text("API 사용 중지"), a:has-text("API 사용 중지"), '
    'button:has-text("Disable"), a:has-text("Disable")'
)

_SEL_EXTERNAL     = (
    'input[type=radio][value="EXTERNAL"], '
    'label:has-text("외부"), label:has-text("External")'
)
_SEL_APP_NAME     = 'input[formcontrolname="displayName"], input[id*="application"]'
_SEL_SAVE_CONT    = 'button:has-text("저장 후 계속"), button:has-text("Save and Continue")'
_SEL_NEXT_STEP    = '[class*="stepper"], [class*="step-"], form, .cfc-form'

_SEL_CRED_BTN     = (
    'button:has-text("인증 정보 만들기"), button:has-text("Create Credentials"), '
    'a:has-text("인증 정보 만들기"), a:has-text("Create Credentials")'
)
_SEL_OAUTH_ITEM   = (
    'button:has-text("OAuth 클라이언트 ID"), li:has-text("OAuth 클라이언트 ID"), '
    'button:has-text("OAuth client ID"), a:has-text("OAuth client ID")'
)
_SEL_APP_TYPE     = 'mat-select, select[formcontrolname="applicationType"]'
_SEL_DESKTOP_OPT  = (
    'mat-option:has-text("데스크톱"), mat-option:has-text("Desktop"), '
    'option:has-text("데스크톱"), option:has-text("Desktop")'
)
_SEL_DIALOG       = '[role="dialog"], mat-dialog-container'
_SEL_JSON_DL      = (
    'button[aria-label*="JSON"], a[aria-label*="JSON"], '
    'button:has-text("JSON 다운로드"), a:has-text("JSON 다운로드"), '
    'button[title*="JSON"], a[title*="JSON"]'
)


# ── 단계별 함수 ───────────────────────────────────────────────────────

def step_create_project(page) -> str | None:
    """1단계: 프로젝트 생성. 성공 시 프로젝트 ID 반환, 실패 시 None."""
    print("\n[1단계] 프로젝트 생성")

    # 페이지 이동 후 입력창 등장까지 최대 15초 대기
    if not page_goto_wait(page, GOOGLE_URLS["console_project_create"], _SEL_PROJECT_NAME,
                          timeout=15000):
        print("  ⚠  프로젝트 생성 페이지 로드 실패 — 실제 페이지 상태 확인:")
        page_inspect(page, "project-create")
        return None

    # 프로젝트 이름 입력 (input_value 검증 내장)
    if not page_wait_type(page, _SEL_PROJECT_NAME, PROJECT_NAME, timeout=8000):
        print("  ⚠  프로젝트 이름 입력 실패")
        page_inspect(page, "project-name-input")
        return None

    # 프로젝트 ID 읽기 (자동 생성된 값 — URL에 사용)
    project_id = None
    try:
        id_el = page.query_selector('#p6ntest-id-input, input[id*="proj-id"], #project-id')
        if id_el:
            project_id = id_el.input_value().strip()
    except Exception:
        pass
    if not project_id:
        project_id = PROJECT_NAME  # fallback: 이름을 ID로 사용

    # 만들기 클릭 → 네트워크+DOM+폴링 3중 검증
    result = page_submit_and_verify(
        page,
        submit_selector=_SEL_CREATE_BTN,
        network_pattern="cloudresourcemanager",
        dom_watch_selector="body",
        result_selector=_SEL_DASHBOARD,
        verify_timeout=30.0,
    )
    print(f"  {result.summary()} | project_id={project_id}")
    return project_id


def step_enable_api(page, name: str, url: str, project_id: str = "") -> None:
    """2단계 개별 API 활성화."""
    print(f"  [{name}] 접속 중...")

    # 프로젝트 ID를 URL에 명시해야 버튼이 활성화됨
    if project_id and "project=" not in url:
        url = f"{url}?project={project_id}"

    already = page_goto_wait(page, url, _SEL_API_ACTIVE, timeout=5000)
    if already:
        print(f"  ✓ {name} 이미 활성화됨")
        return

    # Enable 버튼 등장 신호 → 클릭 → 네트워크+DOM 검증
    if not page_wait_visible(page, _SEL_API_ENABLE, timeout=20000):
        print(f"  ⚠  {name} Enable 버튼 미등장 — 실제 페이지 상태 확인:")
        page_inspect(page, f"api-{name[:20]}")
        return

    result = page_submit_and_verify(
        page,
        submit_selector=_SEL_API_ENABLE,
        network_pattern="serviceusage",           # API 활성화 요청
        dom_watch_selector="body",
        result_selector=_SEL_API_ACTIVE,
        poll_selector=_SEL_API_ACTIVE,
        poll_check=lambda t: bool(t),             # 사용 중지 버튼 텍스트 등장 확인
        verify_timeout=20.0,
    )
    print(f"  {result.summary()}")


def step_oauth_consent(page) -> bool:
    """3단계: OAuth 동의 화면."""
    print("\n[3단계] OAuth 동의 화면 설정")

    if not page_goto_wait(page, GOOGLE_URLS["console_consent"], _SEL_EXTERNAL):
        print("  ⚠  동의 화면 페이지 로드 실패 — 실제 페이지 상태 확인:")
        page_inspect(page, "consent")
        return False

    # External 클릭 → 만들기 버튼 신호
    page_click_then_wait(page, _SEL_EXTERNAL, _SEL_CREATE_BTN,
                          click_timeout=8000, wait_timeout=8000)

    # 만들기 클릭 → 앱 이름 입력창 신호
    if not page_click_then_wait(page, _SEL_CREATE_BTN, _SEL_APP_NAME,
                                 click_timeout=8000, wait_timeout=15000):
        print("  ⚠  동의 화면 폼 로드 실패 — 실제 페이지 상태 확인:")
        page_inspect(page, "consent-form")
        return False

    # 앱 이름 입력 (input_value 검증 내장)
    page_wait_type(page, _SEL_APP_NAME, PROJECT_NAME, timeout=5000)

    # 이메일 입력창 모두 채우기
    for el in page.query_selector_all('input[type=email]'):
        el.triple_click()
        el.type(USER_EMAIL, delay=40)

    # 저장 후 계속 × 3 — 각각 네트워크+DOM 검증
    for step_num in range(1, 4):
        result = page_submit_and_verify(
            page,
            submit_selector=_SEL_SAVE_CONT,
            network_pattern="",                   # 폼 저장 요청 (패턴 무관)
            dom_watch_selector="body",
            result_selector=_SEL_NEXT_STEP,
            verify_timeout=12.0,
        )
        print(f"  저장 후 계속 {step_num}/3 → {result.summary()}")
        if result.error_msg:
            print(f"  ✗ 중단: {result.error_msg}")
            return False

    print("  ✓ OAuth 동의 화면 설정 완료")
    return True


def step_create_oauth_client(page) -> bool:
    """4단계: OAuth 클라이언트 ID 생성."""
    print("\n[4단계] OAuth 클라이언트 ID 생성")

    if not page_goto_wait(page, GOOGLE_URLS["console_credentials"], _SEL_CRED_BTN):
        print("  ⚠  인증 정보 페이지 로드 실패 — 실제 페이지 상태 확인:")
        page_inspect(page, "credentials")
        return False

    # 인증 정보 만들기 → OAuth 클라이언트 ID 메뉴 등장
    if not page_click_then_wait(page, _SEL_CRED_BTN, _SEL_OAUTH_ITEM,
                                 click_timeout=10000, wait_timeout=10000):
        print("  ⚠  메뉴 드롭다운 미열림 — 실제 페이지 상태 확인:")
        page_inspect(page, "credentials-menu")
        return False

    # OAuth 클라이언트 ID 선택 → 앱 유형 선택기 등장
    if not page_click_then_wait(page, _SEL_OAUTH_ITEM, _SEL_APP_TYPE,
                                 click_timeout=8000, wait_timeout=12000):
        print("  ⚠  OAuth 클라이언트 폼 로드 실패 — 실제 페이지 상태 확인:")
        page_inspect(page, "oauth-form")
        return False

    # 앱 유형 → 데스크톱 선택 → 이름 입력창 활성화
    if page_click_then_wait(page, _SEL_APP_TYPE, _SEL_DESKTOP_OPT,
                              click_timeout=8000, wait_timeout=8000):
        page_click_then_wait(page, _SEL_DESKTOP_OPT, _SEL_APP_NAME,
                              click_timeout=5000, wait_timeout=8000)

    # 이름 입력 (input_value 검증 내장)
    page_wait_type(page, _SEL_APP_NAME, OAUTH_CLIENT_NAME, timeout=8000)

    # 만들기 클릭 → 네트워크+DOM+다이얼로그 3중 검증
    result = page_submit_and_verify(
        page,
        submit_selector=_SEL_CREATE_BTN,
        network_pattern="credentials",            # OAuth 클라이언트 생성 API
        dom_watch_selector="body",
        result_selector=_SEL_DIALOG,
        poll_selector=_SEL_DIALOG,
        poll_check=lambda t: bool(t),             # 다이얼로그 텍스트 등장 확인
        verify_timeout=15.0,
    )
    print(f"  {result.summary()}")
    if result.error_msg:
        print(f"  ✗ 실패: {result.error_msg}")
        return False

    print("  ✓ OAuth 클라이언트 ID 생성 완료")
    return True


def step_download_credentials(page) -> None:
    """5단계: credentials.json 다운로드."""
    print("\n[5단계] credentials.json 다운로드")

    # 다이얼로그 내 JSON 다운로드 버튼 등장 → 즉시 클릭
    try:
        dl_btn = page.wait_for_selector(_SEL_JSON_DL, timeout=15000, state="visible")
        with page.expect_download(timeout=30000) as dl_info:
            dl_btn.click()
        dl_info.value.save_as(str(CREDENTIALS_FILE))
        print(f"  ✓ 저장 완료: {CREDENTIALS_FILE}")
    except Exception as e:
        print(f"  ⚠  자동 다운로드 실패: {e}")
        candidates = sorted(
            (Path.home() / "Downloads").glob("client_secret_*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if candidates:
            CREDENTIALS_FILE.write_bytes(candidates[0].read_bytes())
            print(f"  ✓ Downloads에서 복사: {candidates[0].name}")
        else:
            print("  ✗ 수동으로 credentials.json을 저장해주세요")


# ── 메인 ─────────────────────────────────────────────────────────────

def setup():
    print("=" * 70)
    print("Google Cloud Console API 설정 (CDP)")
    print("=" * 70)

    page = get_page()
    try:
        project_id = step_create_project(page) or PROJECT_NAME

        print("\n[2단계] API 활성화 (5개)")
        for name, url in GOOGLE_CLOUD_APIS:
            step_enable_api(page, name, url, project_id=project_id)

        if not step_oauth_consent(page):
            print("\n✗ OAuth 동의 화면 설정 실패 — 중단")
            return

        if not step_create_oauth_client(page):
            print("\n✗ OAuth 클라이언트 생성 실패 — 중단")
            return

        step_download_credentials(page)
    finally:
        close_page(page)

    print("\n" + "=" * 70)
    print("Google Cloud API 설정 완료!")
    print("=" * 70)


if __name__ == "__main__":
    setup()
