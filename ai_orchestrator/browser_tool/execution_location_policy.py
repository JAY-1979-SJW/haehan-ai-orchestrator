"""
통합 실행 위치 정책 모듈

외부 웹 작업은 기본적으로 로컬 에이전트(LOCAL_BROWSER_DEFAULT)에서 실행한다.
서버는 내부 처리/공개 API/분석/저장/리포트만 담당한다(SERVER_ALLOWED).

실행 위치:
- LOCAL_BROWSER_DEFAULT: 외부 웹 작업 기본. 로컬 에이전트 실행
- SERVER_ALLOWED: 내부 API/DB/분석/리포트/공개 API만 서버 실행
- USER_DIRECT_ONLY: 사용자가 직접 수행해야 하는 작업
- BLOCKED: 자동화 금지

하위 호환 상수 (레거시):
- SERVER_FIRST: SERVER_ALLOWED의 별칭 (공개 읽기 전용 예외 시나리오)
- SERVER_ONLY: 서버 전용 내부 처리 (SERVER_ALLOWED 하위분류)
- LOCAL_REQUIRED: LOCAL_BROWSER_DEFAULT의 별칭 (기존 코드 호환)
- SERVER_TO_LOCAL_FALLBACK: 레거시 fallback 시나리오

보안 고정 원칙:
- 쿠키/session/password/OTP/인증서 수집 없음
- 투찰/서명/결제/제출 자동화 없음
- wildcard domain 허용 없음
- 서버에서 외부 사이트 브라우저 원격 접속 기본 실행 금지
"""
from __future__ import annotations

from typing import Any

# ── 실행 위치 상수 (신규) ──────────────────────────────────────────────────────

LOCAL_BROWSER_DEFAULT = "LOCAL_BROWSER_DEFAULT"
SERVER_ALLOWED = "SERVER_ALLOWED"
USER_DIRECT_ONLY = "USER_DIRECT_ONLY"
BLOCKED = "BLOCKED"

# ── 하위 호환 레거시 상수 ──────────────────────────────────────────────────────

SERVER_FIRST = SERVER_ALLOWED          # 레거시: 공개 읽기 시나리오
SERVER_ONLY = "SERVER_ONLY"            # 레거시: 내부 전용
LOCAL_REQUIRED = LOCAL_BROWSER_DEFAULT # 레거시: 로컬 필수
SERVER_TO_LOCAL_FALLBACK = "SERVER_TO_LOCAL_FALLBACK"  # 레거시 fallback

_ALL_LOCATIONS: frozenset[str] = frozenset({
    LOCAL_BROWSER_DEFAULT, SERVER_ALLOWED, USER_DIRECT_ONLY, BLOCKED,
    SERVER_ONLY, SERVER_TO_LOCAL_FALLBACK,
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

# ── 로컬 브라우저 기본 실행 action 패턴 ───────────────────────────────────────

_LOCAL_BROWSER_ACTION_PATTERNS: tuple[str, ...] = (
    "login", "cert_auth", "otp_wait", "security_program",
    "government_auth", "financial_auth",
    "open", "navigate", "open_url", "download", "read",
)

# ── 서버 허용 action (내부 처리만) ────────────────────────────────────────────

_SERVER_ALLOWED_ACTIONS: frozenset[str] = frozenset({
    "report_generate", "api_call", "internal",
    "db_query", "backend_api", "analyze", "notify",
    "store", "save_report", "send_notification",
    "public_api", "public_data_fetch",
})

# ── 서버 허용 site_category (내부/공개 API만) ─────────────────────────────────

_SERVER_ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    "public_readonly",
    "public_api",
    "internal_api",
    "internal_backend",
    "report",
    "search_result",
    "news",
    "public_data",
})

# ── 로컬 브라우저 기본 site_category (외부 웹 전체) ───────────────────────────

_LOCAL_BROWSER_CATEGORIES: frozenset[str] = frozenset({
    "government_procurement",
    "government_procurement_auth",
    "government_procurement_readonly",
    "government_tax",
    "government_tax_auth",
    "financial_banking",
    "financial_banking_auth",
    "financial_card",
    "financial_card_auth",
    "financial_insurance",
    "insurance_auth",
    "association",
    "external_web",
    "certificate_auth",
    "otp_auth",
    "security_program_required",
    "unknown",
})

_USER_GUIDE_KO = (
    "이 작업은 사용자 PC에서 실행됩니다.\n"
    "브라우저가 열리면 필요한 경우 직접 인증해 주세요.\n"
    "비밀번호, OTP, 인증서 비밀번호는 앱이 저장하지 않습니다."
)


def classify_execution_location(task: dict[str, Any]) -> dict[str, Any]:
    """
    task를 분석하여 실행 위치를 분류한다.

    외부 웹 작업은 LOCAL_BROWSER_DEFAULT가 기본값이다.
    서버는 내부/공개 API/분석/저장/리포트만 허용한다.

    task 입력 필드:
      action, target_url, domain, site_category,
      readonly, requires_user_presence

    반환:
      execution_location, reason, fallback_allowed, user_message_ko
    """
    action: str = (task.get("action") or "").lower().strip()
    site_category: str = (task.get("site_category") or "").lower().strip()
    requires_user_presence: bool = bool(task.get("requires_user_presence", False))

    # 1. 절대 차단 action
    if action in _BLOCKED_ACTIONS or any(p in action for p in ("cookie_export", "session_export", "npki")):
        return _result(BLOCKED, f"차단 action: {action!r}", fallback_allowed=False)

    # 2. 사용자 직접 수행
    if action in _USER_DIRECT_ACTIONS or requires_user_presence:
        return _result(USER_DIRECT_ONLY, f"사용자 직접 수행: {action!r}", fallback_allowed=False)

    # 3. 서버 전용 내부 작업
    if action in ("db_query", "backend_api", "internal"):
        return _result(SERVER_ONLY, f"서버 전용 내부: {action!r}", fallback_allowed=False)

    # 4. 서버 허용 action (내부/공개 처리)
    if action in _SERVER_ALLOWED_ACTIONS:
        return _result(SERVER_ALLOWED, f"서버 허용 action: {action!r}", fallback_allowed=False)

    # 5. 서버 허용 category (내부/공개 API/리포트)
    if site_category in _SERVER_ALLOWED_CATEGORIES:
        return _result(SERVER_ALLOWED, f"서버 허용 카테고리: {site_category!r}", fallback_allowed=False)

    # 6. 로컬 브라우저 기본 category (외부 웹)
    if site_category in _LOCAL_BROWSER_CATEGORIES:
        return _result(LOCAL_BROWSER_DEFAULT, f"외부 웹 로컬 기본: {site_category!r}")

    # 7. 외부 URL 감지 (target_url 있는 경우)
    target_url: str = (task.get("target_url") or "").lower()
    if target_url and not target_url.startswith(("http://internal", "https://internal")):
        return _result(LOCAL_BROWSER_DEFAULT, "외부 URL 로컬 기본 실행")

    # 8. 기본: 로컬 브라우저 실행
    return _result(LOCAL_BROWSER_DEFAULT, "기본 정책: 외부 웹 로컬 브라우저 실행")


def is_local_browser_default(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] == LOCAL_BROWSER_DEFAULT


def is_server_allowed(task: dict[str, Any]) -> bool:
    return classify_execution_location(task)["execution_location"] in (
        SERVER_ALLOWED, SERVER_ONLY
    )


def is_server_first(task: dict[str, Any]) -> bool:
    """레거시 호환. SERVER_ALLOWED와 동일."""
    return is_server_allowed(task)


def is_local_required(task: dict[str, Any]) -> bool:
    """레거시 호환. LOCAL_BROWSER_DEFAULT와 동일."""
    return is_local_browser_default(task)


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
        LOCAL_BROWSER_DEFAULT: _USER_GUIDE_KO,
        SERVER_ALLOWED: "서버에서 처리합니다.",
        SERVER_ONLY: "서버 내부에서만 처리합니다.",
        SERVER_TO_LOCAL_FALLBACK: "서버 실패로 사용자 PC에서 계속 진행됩니다.",
        USER_DIRECT_ONLY: "이 작업은 사용자가 직접 수행해야 합니다.",
        BLOCKED: "이 작업은 자동화가 금지되어 있습니다.",
    }
    _no_fallback = {USER_DIRECT_ONLY, BLOCKED, SERVER_ONLY, SERVER_ALLOWED}
    return {
        "execution_location": location,
        "reason": reason,
        "fallback_allowed": fallback_allowed and location not in _no_fallback,
        "user_message_ko": _MSG.get(location, ""),
    }
