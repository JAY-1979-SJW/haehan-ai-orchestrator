"""프로젝트 전역 설정 — 하드코딩 값 중앙 관리.

모든 스크립트에서 직접 값을 쓰지 말고 이 모듈에서 import.

사용법:
    from scripts.common.config import CDP_PORT, USER_EMAIL, GOOGLE_URLS, NAVER_URLS
"""

from __future__ import annotations

from typing import Any

# ── 사용자 정보 ──────────────────────────────────────────────────────
USER_EMAIL = "skyjwshin@gmail.com"
PROJECT_NAME = "haehan-orchestrator"
OAUTH_CLIENT_NAME = "haehan-cli"

# ── CDP 브라우저 ─────────────────────────────────────────────────────
CDP_PORT = 9222
CDP_HOST = "127.0.0.1"
CDP_ENDPOINT = f"http://{CDP_HOST}:{CDP_PORT}"

# ── CDP 데몬 브라우저 정책(단일 출처) ───────────────────────────────────
# 데몬(cdp_daemon.py)·cdp_force_start.py 가 이 값을 읽는다. 값의 뜻·근거: docs/architecture/CDP_BROWSER_POLICY.md
# 아래 세 불리언은 끄면 안 된다 — 검증 함수(browser_lifecycle.validate_policy)와 시험이 True 가 아니면 실패시킨다.
CDP_BROWSER_POLICY: dict[str, Any] = {
    "start_url": "https://www.google.com/",  # 시작 페이지(홈): 옛 탭을 정리한 뒤 이 주소 탭 하나만 남긴다(구글 첫 화면, 로그인·동작 없음)
    "restore_last_session": True,  # 이전 세션 복원 스위치(값 없이) — 로그인(세션 쿠키)이 재시작 뒤에도 남는 조건
    "clean_start": True,  # 시작 직후 복원된 옛 탭 정리
    "graceful_stop_first": True,  # 종료는 CDP Browser.close 먼저 — 쿠키가 디스크에 남는 유일한 종료 방식
    "restore_settle_s": 10.0,  # 세션 복원이 끝나기를 기다리는 최대 시간(초)
}
CDP_START_URL = CDP_BROWSER_POLICY["start_url"]

# ── Google 서비스 URL ────────────────────────────────────────────────
GOOGLE_URLS = {
    # 데몬 브라우저 시작 페이지(구글 홈)
    "home": CDP_START_URL,
    # Calendar
    "calendar_day": "https://calendar.google.com/calendar/u/0/r/day",
    "calendar_week": "https://calendar.google.com/calendar/u/0/r/week",
    "calendar_home": "https://calendar.google.com/calendar/u/0/r",
    # Gmail
    "gmail_inbox": "https://mail.google.com/mail/u/0/#inbox",
    "gmail_sent": "https://mail.google.com/mail/u/0/#sent",
    "gmail_drafts": "https://mail.google.com/mail/u/0/#drafts",
    "gmail_archive": "https://mail.google.com/mail/u/0/#all",
    "gmail_trash": "https://mail.google.com/mail/u/0/#trash",
    "gmail_home": "https://mail.google.com/mail/u/0/",
    # Drive
    "drive_home": "https://drive.google.com/drive/u/0/",
    # Docs
    "docs_home": "https://docs.google.com/document/u/0/",
    "docs_create": "https://docs.google.com/document/create",
    # Sheets
    "sheets_home": "https://docs.google.com/spreadsheets/u/0/",
    "sheets_create": "https://docs.google.com/spreadsheets/create",
    # Cloud Console
    "console_project_create": "https://console.cloud.google.com/projectcreate",
    "console_credentials": "https://console.cloud.google.com/apis/credentials",
    "console_consent": "https://console.cloud.google.com/apis/credentials/consent",
}

# ── Google Cloud API 활성화 목록 ─────────────────────────────────────
GOOGLE_CLOUD_APIS = [
    ("Google Calendar API", "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"),
    ("Gmail API", "https://console.cloud.google.com/apis/library/gmail.googleapis.com"),
    ("Google Drive API", "https://console.cloud.google.com/apis/library/drive.googleapis.com"),
    ("Google Docs API", "https://console.cloud.google.com/apis/library/docs.googleapis.com"),
    ("Google Sheets API", "https://console.cloud.google.com/apis/library/sheets.googleapis.com"),
]

# ── 네이버 서비스 URL ────────────────────────────────────────────────
NAVER_URLS = {
    "home": "https://www.naver.com/",
    "blog_home": "https://section.blog.naver.com/BlogHome.naver",
    "blog_write": "https://blog.naver.com/new",
    "cafe_home": "https://cafe.naver.com/",
}

# ── 로그인 확인용 프로브 URL ─────────────────────────────────────────
LOGIN_PROBE_URLS = {
    "google": "https://www.google.com/",
    "naver": "https://www.naver.com/",
    "kakao": "https://accounts.kakao.com/",
    "youtube": "https://www.youtube.com/",
    "github": "https://github.com/",
}
