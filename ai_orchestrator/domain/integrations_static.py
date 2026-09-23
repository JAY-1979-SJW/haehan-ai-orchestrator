"""연동 서비스 정적 목록 (L1 공유 계약).

ops_router 모듈(L8)의 GET /api/v1/ops/integrations 응답과
domain/model_adapters 모듈의 Integration 모델 변환이 공유하는
단일 source of truth. 값 자체는 변경하지 않고 위치만 이동한다.

주의:
- API 응답 key/구조 변경 금지 — ops_router 모듈의 _STATIC_INTEGRATIONS 는
  이 모듈의 STATIC_INTEGRATIONS 를 그대로 re-export 한다.
"""

from __future__ import annotations

STATIC_INTEGRATIONS = [
    {
        "key": "naver-search",
        "name": "Naver 검색 (read-only)",
        "classification": "SERVER_READONLY_ALLOWED",
        "connected": True,
        "authMethod": "none",
        "notes": "/api/v1/external/naver/* 3개 endpoint 활성화됨",
    },
    {
        "key": "naver-local-agent",
        "name": "Naver 로컬 에이전트 업무",
        "classification": "LOCAL_AGENT_REQUIRED",
        "connected": False,
        "authMethod": "browser_session",
        "notes": "로컬 에이전트 + 사전 로그인 필요",
        "action": "로컬 에이전트 설정",
    },
    {
        "key": "google-oauth",
        "name": "Google OAuth/API",
        "classification": "OFFICIAL_API_OR_OAUTH_REQUIRED",
        "connected": False,
        "authMethod": "oauth",
        "notes": "credentials.json + token.json 설정 필요",
        "action": "OAuth 설정 시작",
    },
    {
        "key": "telegram",
        "name": "Telegram 알림",
        "classification": "IN_SCOPE",
        "connected": True,
        "authMethod": "bot_token",
        "notes": "BOT_TOKEN env 설정됨. 승인 알림 발송 활성화",
    },
    {
        "key": "cad-app",
        "name": "CAD 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
    {
        "key": "hwpx-app",
        "name": "HWPX 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
    {
        "key": "excel-app",
        "name": "Excel/Office 앱 연동",
        "classification": "EXTERNAL_APP_HOLD",
        "connected": False,
        "authMethod": "none",
        "notes": "별도 앱 개발 완료 후 연결통로 공사 예정",
    },
]
