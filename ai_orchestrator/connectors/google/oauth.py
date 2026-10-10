"""공용 Google OAuth2 인증 — Gmail/Calendar/Drive 등 여러 서비스가 같은 자격증명을 공유.

project: haehan-ai (기존 gmail_reader.py·YouTube OAuth와 동일 GCP 프로젝트, 2026-09-29
실측 확인: gmail_credentials.json의 project_id 필드). 새 서비스를 추가할 때마다 별도
자격증명을 새로 발급받지 않고, 여기 SCOPES 에 스코프만 추가하면 된다.

스코프 확장 시 기존 토큰 파일이 새 스코프를 포함하지 않으면 자동으로 재동의 플로우를
띄운다(로컬 브라우저 팝업, 사용자 승인 1회 필요 — 로그인/동의는 AI가 대신 못 함,
CLAUDE.md 예외사항). google-auth 공식 문서: "OAuth 2.0 credentials can not request
additional scopes after authorization" — 저장된 토큰은 스코프를 나중에 못 늘리므로
부족하면 반드시 InstalledAppFlow를 처음부터 다시 돌려야 한다.

L3 Connectors 계층. 업무 로직 없음.
"""

from __future__ import annotations

import logging

from ai_orchestrator.core.config import GMAIL_CREDENTIALS_PATH, GMAIL_TOKEN_PATH

logger = logging.getLogger(__name__)

# 서비스 추가 시 여기에 스코프만 추가 — 기존 코드(gmail_reader.py) 하위호환 위해
# gmail.readonly 는 그대로 유지.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials():
    """OAuth2 인증 후 Credentials 반환. 토큰이 없거나 스코프가 부족하면 재동의."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_PATH), SCOPES)
        # 기존 토큰(예: gmail.readonly만 있던 구 버전)이 새로 추가된 스코프를 못 갖고
        # 있으면 그대로 쓰지 않고 재동의를 강제한다 — 안 그러면 API가 나중에
        # insufficient scope 403으로 조용히 실패한다(google-auth 공식 문서: 저장된
        # 토큰은 발급 후 스코프를 못 늘림).
        if creds and creds.scopes and not set(SCOPES).issubset(set(creds.scopes)):
            logger.info("[google_oauth] 토큰 스코프 부족 — 재동의 필요 (기존=%s)", creds.scopes)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GMAIL_CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials 없음: {GMAIL_CREDENTIALS_PATH}\n"
                    "Google Cloud Console에서 OAuth2 credentials.json을 다운받아 해당 경로에 저장하세요."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        GMAIL_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds


def build_service(name: str, version: str):
    """지정한 Google API(name, version) 서비스 객체 반환. 예: build_service('calendar', 'v3')."""
    from googleapiclient.discovery import build

    return build(name, version, credentials=get_credentials())
