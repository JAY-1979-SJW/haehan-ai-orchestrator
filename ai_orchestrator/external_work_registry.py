"""외부 웹 업무 레지스트리 — 실행 위치·인증 방식·범위 분류.

비서앱이 현재 또는 향후 지원할 외부 웹 업무를 한 곳에 명시한다.
실제 실행이 가능한 항목은 web_task_registry.py에 등록된다.
여기에 있는 항목은 정책·위치·인증 분류 기준만 제공한다.

분류값:
  SERVER_READONLY_ALLOWED     — 서버에서 공개 read-only 실행 가능
  OFFICIAL_API_OR_OAUTH_REQUIRED — 공식 API/OAuth 설정 완료 후 실행 가능
  LOCAL_AGENT_REQUIRED        — 사용자 PC 로컬 에이전트 필요
  USER_DIRECT_REQUIRED        — 사용자 직접 조작 필요 (비밀번호/OTP/전자서명 등)
  WEB_TASK_REGISTRY           — web_task_registry.py에 이미 등록됨 (approval gate 완비)
  QUARANTINE_OR_HOLD          — 현재 차단/보류 상태 (보안 검토 전)

실행 위치:
  SERVER         — 서버 브라우저 또는 서버 API 직접 실행 가능
  LOCAL_AGENT    — 사용자 PC 로컬 에이전트만 실행 가능
  USER_DIRECT    — 사용자가 직접 실행해야 함 (비서앱은 상태 표시만)
  OFFICIAL_API   — 공식 API/OAuth client 설정 후 서버 실행 가능

위험도:
  low    — 공개 read-only, 부작용 없음
  medium — 조회/열람, 계정 인증 필요
  high   — 쓰기·게시·수정·삭제·제출 포함
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExternalWorkEntry:
    work_key: str               # "{provider}/{work_type}"
    provider: str
    work_type: str
    description: str
    classification: str         # 분류값
    execution_location: str     # SERVER / LOCAL_AGENT / USER_DIRECT / OFFICIAL_API
    risk_level: str             # low / medium / high
    requires_approval: bool
    requires_auth: bool         # 계정 인증 필요 여부
    auth_method: str            # none / oauth / browser_session / user_direct
    registered_in_web_task: bool  # web_task_registry.py에 등록 여부
    notes: str = ""


_ENTRIES: list[ExternalWorkEntry] = [

    # ── Naver: read-only 검색 (SERVER_READONLY_ALLOWED) ──────────────────────
    ExternalWorkEntry(
        work_key="naver/blog_search",
        provider="naver",
        work_type="blog_search",
        description="네이버 블로그 검색 결과 조회 (DB 기반, read-only)",
        classification="SERVER_READONLY_ALLOWED",
        execution_location="SERVER",
        risk_level="low",
        requires_approval=False,
        requires_auth=True,
        auth_method="none",
        registered_in_web_task=False,
        notes="naver_search_router /api/v1/external/naver/blog-search 로 제공. admin/owner only.",
    ),
    ExternalWorkEntry(
        work_key="naver/shopping_search",
        provider="naver",
        work_type="shopping_search",
        description="네이버 쇼핑 검색 결과 조회 (DB 기반, read-only)",
        classification="SERVER_READONLY_ALLOWED",
        execution_location="SERVER",
        risk_level="low",
        requires_approval=False,
        requires_auth=False,
        auth_method="none",
        registered_in_web_task=False,
        notes="naver_search_router /api/v1/external/naver/shopping-search 로 제공.",
    ),
    ExternalWorkEntry(
        work_key="naver/search_status",
        provider="naver",
        work_type="search_status",
        description="네이버 검색 수집 상태 조회 (read-only)",
        classification="SERVER_READONLY_ALLOWED",
        execution_location="SERVER",
        risk_level="low",
        requires_approval=False,
        requires_auth=False,
        auth_method="none",
        registered_in_web_task=False,
        notes="naver_search_router /api/v1/external/naver/status 로 제공.",
    ),

    # ── Naver: 개발자 앱 등록 (WEB_TASK_REGISTRY — 이미 등록됨) ───────────────
    ExternalWorkEntry(
        work_key="naver/app_register",
        provider="naver",
        work_type="app_register",
        description="네이버 개발자 센터 앱 등록 (브라우저 폼 자동 입력, 승인 필요)",
        classification="WEB_TASK_REGISTRY",
        execution_location="LOCAL_AGENT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="browser_session",
        registered_in_web_task=True,
        notes="사전 로그인 세션 필요. web_task_registry naver/app_register 등록됨.",
    ),

    # ── Naver: 블로그 작성/게시 (LOCAL_AGENT_REQUIRED) ────────────────────────
    ExternalWorkEntry(
        work_key="naver/blog_write",
        provider="naver",
        work_type="blog_write",
        description="네이버 블로그 글 작성/게시 (로컬 에이전트 + 사용자 승인 필요)",
        classification="LOCAL_AGENT_REQUIRED",
        execution_location="LOCAL_AGENT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="browser_session",
        registered_in_web_task=False,
        notes="서버 브라우저 금지. local_agent/browser/mixins/blog_mixin.py 구현 있음. "
              "실제 게시는 사용자 승인 후 로컬 에이전트가 수행.",
    ),
    ExternalWorkEntry(
        work_key="naver/cafe_post",
        provider="naver",
        work_type="cafe_post",
        description="네이버 카페 게시글 작성/게시 (로컬 에이전트 + 사용자 승인 필요)",
        classification="LOCAL_AGENT_REQUIRED",
        execution_location="LOCAL_AGENT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="browser_session",
        registered_in_web_task=False,
        notes="서버 브라우저 금지. local_agent/browser/mixins/cafe_mixin.py 구현 있음.",
    ),
    ExternalWorkEntry(
        work_key="naver/mail_send",
        provider="naver",
        work_type="mail_send",
        description="네이버 메일 발송 (로컬 에이전트 + 사용자 직접 확인 필요)",
        classification="USER_DIRECT_REQUIRED",
        execution_location="USER_DIRECT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="browser_session",
        registered_in_web_task=False,
        notes="메일 발송은 사용자가 직접 확인 후 실행. local_agent/browser/mixins/mail_mixin.py.",
    ),

    # ── Google: 공식 API/OAuth 계열 ──────────────────────────────────────────
    ExternalWorkEntry(
        work_key="google/oauth_submit",
        provider="google",
        work_type="oauth_submit",
        description="Google Cloud Console OAuth 클라이언트 등록 (승인 필요)",
        classification="WEB_TASK_REGISTRY",
        execution_location="LOCAL_AGENT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="browser_session",
        registered_in_web_task=True,
        notes="web_task_registry google/oauth_submit 등록됨. 사전 로그인 세션 필요.",
    ),
    ExternalWorkEntry(
        work_key="google/gmail_read",
        provider="google",
        work_type="gmail_read",
        description="Gmail 수신함 조회 (공식 Gmail API + OAuth2)",
        classification="OFFICIAL_API_OR_OAUTH_REQUIRED",
        execution_location="OFFICIAL_API",
        risk_level="medium",
        requires_approval=False,
        requires_auth=True,
        auth_method="oauth",
        registered_in_web_task=False,
        notes="gmail_reader.py 구현 있음. credentials.json + token.json 설정 필요. "
              "server /api/v1/inbox/email/fetch 엔드포인트로 제공.",
    ),
    ExternalWorkEntry(
        work_key="google/calendar_read",
        provider="google",
        work_type="calendar_read",
        description="Google Calendar 일정 조회 (공식 Calendar API + OAuth2)",
        classification="OFFICIAL_API_OR_OAUTH_REQUIRED",
        execution_location="OFFICIAL_API",
        risk_level="medium",
        requires_approval=False,
        requires_auth=True,
        auth_method="oauth",
        registered_in_web_task=False,
        notes="calendar_mixin.py 로컬 에이전트 참조 있음. 공식 API client 미구현. FUTURE_INTEGRATION.",
    ),
    ExternalWorkEntry(
        work_key="google/drive_read",
        provider="google",
        work_type="drive_read",
        description="Google Drive 파일 조회 (공식 Drive API + OAuth2)",
        classification="OFFICIAL_API_OR_OAUTH_REQUIRED",
        execution_location="OFFICIAL_API",
        risk_level="medium",
        requires_approval=False,
        requires_auth=True,
        auth_method="oauth",
        registered_in_web_task=False,
        notes="공식 Drive API client 미구현. FUTURE_INTEGRATION.",
    ),
    ExternalWorkEntry(
        work_key="google/browser_login",
        provider="google",
        work_type="browser_login",
        description="Google 계정 브라우저 로그인 자동화 — 금지",
        classification="QUARANTINE_OR_HOLD",
        execution_location="USER_DIRECT",
        risk_level="high",
        requires_approval=True,
        requires_auth=True,
        auth_method="user_direct",
        registered_in_web_task=False,
        notes="서버 브라우저 Google 로그인 자동화 금지. execution_location_guard 차단 대상.",
    ),
]

_REGISTRY: dict[str, ExternalWorkEntry] = {e.work_key: e for e in _ENTRIES}


def get_external_work(provider: str, work_type: str) -> ExternalWorkEntry | None:
    return _REGISTRY.get(f"{provider}/{work_type}")


def list_external_works(
    provider: str | None = None,
    classification: str | None = None,
) -> list[dict]:
    """외부 웹 업무 목록 반환 (필터 선택)."""
    entries = _ENTRIES
    if provider:
        entries = [e for e in entries if e.provider == provider]
    if classification:
        entries = [e for e in entries if e.classification == classification]
    return [
        {
            "work_key": e.work_key,
            "provider": e.provider,
            "work_type": e.work_type,
            "description": e.description,
            "classification": e.classification,
            "execution_location": e.execution_location,
            "risk_level": e.risk_level,
            "requires_approval": e.requires_approval,
            "requires_auth": e.requires_auth,
            "auth_method": e.auth_method,
            "registered_in_web_task": e.registered_in_web_task,
            "notes": e.notes,
        }
        for e in entries
    ]


__all__ = ["ExternalWorkEntry", "get_external_work", "list_external_works"]
