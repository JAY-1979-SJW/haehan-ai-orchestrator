"""
통합 실행 위치 정책 모듈

사이트별 전용 도구를 만들지 않는다.
사이트별 특성은 domain profile과 security signal로만 관리한다.

실행 위치:
- SERVER_FIRST: 서버에서 먼저, 실패 시 로컬 fallback 가능
- SERVER_ONLY: 서버에서만 (내부 백엔드 작업)
- LOCAL_REQUIRED: 처음부터 로컬 에이전트 필요
- SERVER_TO_LOCAL_FALLBACK: 서버 시도 후 실패 시 로컬 전환
- USER_DIRECT_ONLY: 사용자가 직접 수행해야 하는 작업
- BLOCKED: 자동화 금지

보안 고정 원칙:
- 쿠키/session/password/OTP/인증서 수집 없음
- 투찰/서명/결제/제출 자동화 없음
- wildcard domain 허용 없음
"""
from __future__ import annotations

from typing import Any

# ── 실행 위치 상수 ─────────────────────────────────────────────────────────────

SERVER_FIRST = "SERVER_FIRST"
SERVER_ONLY = "SERVER_ONLY"
LOCAL_REQUIRED = "LOCAL_REQUIRED"
SERVER_TO_LOCAL_FALLBACK = "SERVER_TO_LOCAL_FALLBACK"
USER_DIRECT_ONLY = "USER_DIRECT_ONLY"
BLOCKED = "BLOCKED"

_ALL_LOCATIONS: frozenset[str] = frozenset({
    SERVER_FIRST, SERVER_ONLY, LOCAL_REQUIRED,
    SERVER_TO_LOCAL_FALLBACK, USER_DIRECT_ONLY, BLOCKED,
})

# ── 차단 action 키워드 ─────────────────────────────────────────────────────────

_BLOCKED_ACTIONS: frozenset[str] = frozenset({
    "cookie_export", "session_export", "cookie_dump", "session_dump",
    "localStorage_dump", "sessionStorage_dump", "password_save",
    "credential_store", "cert_file_access", "npki_access",
    "auto_sign", "e_signature", "auto_bid_submit", "bid_submit",
    "auto_payment", "auto_transfer", "auto_contract_submit",
    "screenshot_sensitive", "token_export", "auth_header_export",
})

# ── 사용자 직접 수행 action 키워드 ────────────────────────────────────────────

_USER_DIRECT_ACTIONS: frozenset[str] = frozenset({
    "cert_password_input", "otp_input", "final_submit",
    "confirm_payment", "confirm_transfer", "sign_document",
    "e_sign", "bid_final_submit", "contract_confirm",
})

# ── 로컬 필수 action 패턴 ──────────────────────────────────────────────────────

_LOCAL_REQUIRED_ACTION_PATTERNS: tuple[str, ...] = (
    "login", "cert_auth", "otp_wait", "security_program",
    "government_auth", "financial_auth",
)

# ── 서버 우선 허용 action 패턴 ────────────────────────────────────────────────

_SERVER_FIRST_ACTIONS: frozenset[str] = frozenset({
    "open", "read", "search", "navigate", "open_url",
    "public_read", "report_generate", "api_call",
})

# ── 로컬 필수 site_category ───────────────────────────────────────────────────

_LOCAL_REQUIRED_CATEGORIES: frozenset[str] = frozenset({
    "government_procurement_auth",
    "government_tax_auth",
    "financial_banking_auth",
    "financial_card_auth",
    "insurance_auth",
    "certificate_auth",
    "otp_auth",
    "security_program_required",
})

# ── 서버 우선 site_category ───────────────────────────────────────────────────

_SERVER_FIRST_CATEGORIES: frozenset[str] = frozenset({
    "public_readonly",
    "government_procurement_readonly",
    "internal_api",
    "internal_backend",
    "report",
    "search_result",
    "news",
    "public_data",
})


def classify_execution_location(task: dict[str, Any]) -> dict[str, Any]:
    """
    task를 분석하여 실행 위치를 분류한다.

    task 입력 필드:
      action, target_url, domain, site_category,
      readonly, requires_user_presence,
      allow_server_first, allow_local_fallback

    반환:
      execution_location, reason, fallback_allowed, user_message_ko
    """
    action: str = (task.get("action") or "").lower().strip()
    site_category: str = (task.get("site_category") or "").lower().strip()
    readonly: bool = bool(task.get("readonly", True))
    requires_user_presence: bool = bool(task.get("requires_user_presence", False))

    # 1. 절대 차단 action
    if action in _BLOCKED_ACTIONS or any(p in action for p in ("cookie_export", "session_export", "npki")):
        return _result(BLOCKED, f"차단 action: {action!r}", fallback_allowed=False)

    # 2. 사용자 직접 수행
    if action in _USER_DIRECT_ACTIONS or requires_user_presence:
        return _result(USER_DIRECT_ONLY, f"사용자 직접 수행: {action!r}", fallback_allowed=False)

    # 3. 로컬 필수 action 패턴
    if any(p in action for p in _LOCAL_REQUIRED_ACTION_PATTERNS):
        return _result(LOCAL_REQUIRED, f"로컬 필수 action 패턴 감지: {action!r}")

    # 4. 로컬 필수 site_category
    if site_category in _LOCAL_REQUIRED_CATEGORIES:
        return _result(LOCAL_REQUIRED, f"로컬 필수 카테고리: {site_category!r}")

    # 5. 서버 우선 action
    if action in _SERVER_FIRST_ACTIONS and readonly:
        return _result(SERVER_FIRST, f"서버 우선 read-only: {action!r}")

    # 6. 서버 우선 category
    if site_category in _SERVER_FIRST_CATEGORIES:
        return _result(SERVER_FIRST, f"서버 우선 카테고리: {site_category!r}")

    # 7. 내부 백엔드 작업
    if action in ("db_query", "backend_api", "report_generate", "internal"):
        return _result(SERVER_ONLY, f"서버 전용: {action!r}", fallback_allowed=False)

    # 8. 기본: SERVER_FIRST with fallback
    return _result(SERVER_FIRST, "기본 정책: 서버 우선 실행")


def is_server_first(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] in (
        SERVER_FIRST, SERVER_TO_LOCAL_FALLBACK
    )


def is_local_required(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] == LOCAL_REQUIRED


def is_user_direct_only(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] == USER_DIRECT_ONLY


def should_block(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] == BLOCKED


def get_execution_reason(task: dict[str, Any]) -> str:
    return classify_execution_location(task)["reason"]


def _result(
    location: str,
    reason: str,
    fallback_allowed: bool = True,
) -> dict[str, Any]:
    _MSG = {
        SERVER_FIRST: "서버에서 실행합니다.",
        SERVER_ONLY: "서버 내부에서만 처리합니다.",
        LOCAL_REQUIRED: "이 작업은 사용자 PC에서 계속 진행됩니다.",
        SERVER_TO_LOCAL_FALLBACK: "서버 실패로 사용자 PC에서 계속 진행됩니다.",
        USER_DIRECT_ONLY: "이 작업은 사용자가 직접 수행해야 합니다.",
        BLOCKED: "이 작업은 자동화가 금지되어 있습니다.",
    }
    return {
        "execution_location": location,
        "reason": reason,
        "fallback_allowed": fallback_allowed and location not in (USER_DIRECT_ONLY, BLOCKED, SERVER_ONLY),
        "user_message_ko": _MSG.get(location, ""),
    }
