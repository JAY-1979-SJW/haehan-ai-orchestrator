"""URL/title/body 텍스트 기반 로그인 상태 분류 — pure 함수.

Playwright/CDP 비의존. 테스트 가능한 단순 분류기.

상태 enum:
  LOGIN_UNKNOWN / LOGIN_REQUIRED / LOGIN_ACTION_STARTED / LOGIN_IN_PROGRESS
  CHALLENGE_REQUIRED / CONSENT_REQUIRED
  LOGGED_IN / LOGIN_FAILED / SESSION_EXPIRED / POPUP_WAITING

설계:
  - 입력은 url, title, body_sample(짧은 텍스트, ≤8KB) 만 받는다.
  - 사용자 password/OTP/쿠키 원문은 절대 받지 않는다.
  - 분류 결과에는 sub-signals 만 포함 (수치/boolean).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

# ── 상태 ─────────────────────────────────────────────────────────────

LOGIN_UNKNOWN = "LOGIN_UNKNOWN"
LOGIN_REQUIRED = "LOGIN_REQUIRED"
LOGIN_ACTION_STARTED = "LOGIN_ACTION_STARTED"
LOGIN_IN_PROGRESS = "LOGIN_IN_PROGRESS"
CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
CONSENT_REQUIRED = "CONSENT_REQUIRED"
LOGGED_IN = "LOGGED_IN"
LOGIN_FAILED = "LOGIN_FAILED"
SESSION_EXPIRED = "SESSION_EXPIRED"
POPUP_WAITING = "POPUP_WAITING"


# ── URL/title/body 패턴 카탈로그 ──────────────────────────────────────

GOOGLE_AUTH_HOSTS = (
    "accounts.google.com",
    "accounts.youtube.com",
    "oauth2.googleapis.com",
)

LOGIN_HOST_HINTS = (
    "login",
    "signin",
    "sign-in",
    "auth",
    "nidlogin",
    "accounts.",
    "id.",
    "passport.",
)

LOGIN_PATH_PATTERNS = (
    "/login",
    "/signin",
    "/sign-in",
    "/sign_in",
    "/auth",
    "/ServiceLogin",
    "/account/login",
    "/users/sign_in",
)

ACCOUNT_PICKER_URL_PATTERNS = (
    "accountchooser",
    "selectaccount",
    "select_account",
    "chooseaccount",
    "/signin/v2/identifier",
    "/identifier",
    "ServiceLogin",
)

CHALLENGE_URL_PATTERNS = (
    "/challenge",
    "/signin/challenge",
    "/v2/challenge",
    "/verify",
    "/2-step",
    "twofactor",
    "two-factor",
    "totp",
    "/otp",
    "smsauth",
    "phone-verification",
)

CHALLENGE_TEXT_PATTERNS = (
    "2-Step Verification",
    "2단계 인증",
    "2단계인증",
    "Two-Step",
    "Verify it's you",
    "본인 확인",
    "본인확인",
    "휴대전화로 받은 코드",
    "Enter the code",
    "코드 입력",
    "OTP",
    "일회용 비밀번호",
    "보안 카드",
    "보안카드",
    "보안 문자",
    "기기 승인",
    "passkey",
    "패스키",
    "biometric",
    "생체 인증",
    "생체인증",
)

CONSENT_URL_PATTERNS = (
    "/oauth/consent",
    "/o/oauth2/auth",
    "/oauth2/auth",
    "/consent",
    "/permissions",
    "/authorize",
)

CONSENT_TEXT_PATTERNS = (
    "Grant access",
    "Allow",
    "권한을 허용",
    "권한 허용",
    "동의",
    "consent",
    "permissions",
    "Sign in to your account to continue",
)

LOGGED_IN_TEXT_PATTERNS = (
    "로그아웃",
    "Sign out",
    "Log out",
    "sign out",
    "logout",
    "마이페이지",
    "내정보",
    "내 정보",
    "My Page",
    "My Account",
    "프로필",
    "Profile",
)

LOGGED_IN_GREETING_PATTERNS = (
    re.compile(r"([가-힣A-Za-z0-9_.\-]{2,20})\s*님"),
    re.compile(r"Hello[,!\s]+([A-Za-z0-9._-]{2,30})", re.I),
    re.compile(r"Welcome[,!\s]+([A-Za-z0-9._-]{2,30})", re.I),
)

LOGIN_BUTTON_TEXT_PATTERNS = (
    "Sign in",
    "Sign In",
    "Log in",
    "Log In",
    "Login",
    "로그인",
    "Google로 로그인",
    "Sign in with Google",
    "계정 선택",
    "다른 계정",
    "Use another account",
)

LOGIN_FAILED_TEXT_PATTERNS = (
    "비밀번호가 일치하지 않",
    "비밀번호를 다시 확인",
    "Wrong password",
    "incorrect password",
    "잘못된 비밀번호",
    "로그인에 실패",
    "Login failed",
    "Couldn't sign you in",
)

SESSION_EXPIRED_TEXT_PATTERNS = (
    "세션이 만료",
    "session expired",
    "다시 로그인",
    "Please sign in again",
    "Your session has expired",
)


@dataclass
class DetectionResult:
    state: str = LOGIN_UNKNOWN
    reason: str = ""
    is_auth_host: bool = False
    is_account_picker: bool = False
    has_password_field_hint: bool = False
    has_logout_signal: bool = False
    has_greeting: bool = False
    sanitized_url: str = ""
    title: str = ""
    detected_user_hint: str = ""  # 마스킹 적용 후
    sub_signals: dict[str, Any] = field(default_factory=dict)


# ── 유틸 ─────────────────────────────────────────────────────────────


def sanitize_url(url: str) -> str:
    """query/fragment 제거. token/code 등 민감 파라미터 노출 방지."""
    if not url:
        return ""
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        path = p.path or ""
        scheme = p.scheme or "https"
        port = f":{p.port}" if p.port and p.port not in (80, 443) else ""
        return f"{scheme}://{host}{port}{path}"
    except Exception:  # noqa: BLE001 - URL/텍스트 기반 로그인 상태 순수 분류 헬퍼 — sanitize_url/_host/_path/_query가 파싱 실패 시 빈 문자열을 반환할 뿐, 최종 판정(classify)은 예외를 던지지 않는 별도 순수함수이며 비밀번호/OTP 원문은 다루지 않음.
        return ""


def mask_email(text: str) -> str:
    if not text:
        return ""
    return re.sub(
        r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        r"\1***@\2",
        text,
    )


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001 - URL/텍스트 기반 로그인 상태 순수 분류 헬퍼 — sanitize_url/_host/_path/_query가 파싱 실패 시 빈 문자열을 반환할 뿐, 최종 판정(classify)은 예외를 던지지 않는 별도 순수함수이며 비밀번호/OTP 원문은 다루지 않음.
        return ""


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "").lower()
    except Exception:  # noqa: BLE001 - URL/텍스트 기반 로그인 상태 순수 분류 헬퍼 — sanitize_url/_host/_path/_query가 파싱 실패 시 빈 문자열을 반환할 뿐, 최종 판정(classify)은 예외를 던지지 않는 별도 순수함수이며 비밀번호/OTP 원문은 다루지 않음.
        return ""


def _query(url: str) -> str:
    try:
        return (urlparse(url).query or "").lower()
    except Exception:  # noqa: BLE001 - URL/텍스트 기반 로그인 상태 순수 분류 헬퍼 — sanitize_url/_host/_path/_query가 파싱 실패 시 빈 문자열을 반환할 뿐, 최종 판정(classify)은 예외를 던지지 않는 별도 순수함수이며 비밀번호/OTP 원문은 다루지 않음.
        return ""


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(n.lower() in low for n in needles)


def _greeting_user(text: str) -> str:
    if not text:
        return ""
    for pat in LOGGED_IN_GREETING_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return ""


# ── 핵심 분류 ─────────────────────────────────────────────────────────


def classify(
    url: str,
    title: str = "",
    body_sample: str = "",
    *,
    prev_state: str = "",
    has_password_input: bool | None = None,
) -> DetectionResult:
    """url/title/body 텍스트 기반 로그인 상태 분류.

    Args:
        url: 현재 target URL (원본)
        title: 현재 target title
        body_sample: 짧은 페이지 텍스트 샘플 (선택). 비밀번호/OTP 원문 포함 금지.
        prev_state: 이전 상태 (LOGIN_REQUIRED → LOGGED_IN 전이 식별용)
        has_password_input: DOM 측정 결과(있으면). None 이면 미사용.
    """
    host = _host(url)
    path = _path(url)
    query = _query(url)
    s_url = sanitize_url(url)
    title_l = (title or "").strip()

    combined_text = " ".join([title_l, body_sample or ""])[:8000]

    is_auth_host = host in GOOGLE_AUTH_HOSTS or any(h in host for h in LOGIN_HOST_HINTS)
    is_login_path = any(p in path for p in LOGIN_PATH_PATTERNS)
    is_account_picker = any(p in (path + "?" + query) for p in ACCOUNT_PICKER_URL_PATTERNS)

    is_challenge_url = any(p in (path + "?" + query) for p in CHALLENGE_URL_PATTERNS)
    is_challenge_text = _has_any(combined_text, CHALLENGE_TEXT_PATTERNS)

    is_consent_url = any(p in (path + "?" + query) for p in CONSENT_URL_PATTERNS)
    is_consent_text = _has_any(combined_text, CONSENT_TEXT_PATTERNS)

    has_logout = _has_any(combined_text, LOGGED_IN_TEXT_PATTERNS)
    greeting_user = _greeting_user(combined_text)
    has_login_button = _has_any(combined_text, LOGIN_BUTTON_TEXT_PATTERNS)

    has_failed_text = _has_any(combined_text, LOGIN_FAILED_TEXT_PATTERNS)
    has_session_expired = _has_any(combined_text, SESSION_EXPIRED_TEXT_PATTERNS)

    sub_signals: dict[str, Any] = {
        "is_auth_host": is_auth_host,
        "is_login_path": is_login_path,
        "is_account_picker": is_account_picker,
        "is_challenge_url": is_challenge_url,
        "is_challenge_text": is_challenge_text,
        "is_consent_url": is_consent_url,
        "is_consent_text": is_consent_text,
        "has_logout": has_logout,
        "has_greeting": bool(greeting_user),
        "has_login_button": has_login_button,
    }
    if has_password_input is not None:
        sub_signals["has_password_input"] = bool(has_password_input)

    # 우선순위: SESSION_EXPIRED > LOGIN_FAILED > CHALLENGE > CONSENT > LOGGED_IN > LOGIN_REQUIRED
    if has_session_expired:
        state = SESSION_EXPIRED
        reason = "session_expired_text"
    elif has_failed_text:
        state = LOGIN_FAILED
        reason = "login_failed_text"
    elif is_challenge_url or is_challenge_text:
        state = CHALLENGE_REQUIRED
        reason = "challenge_url" if is_challenge_url else "challenge_text"
    elif is_consent_url or is_consent_text:
        state = CONSENT_REQUIRED
        reason = "consent_url" if is_consent_url else "consent_text"
    elif (has_logout or greeting_user) and not (is_login_path or is_auth_host):
        state = LOGGED_IN
        reason = "logout_signal" if has_logout else "greeting"
    elif is_auth_host or is_login_path or has_login_button:
        # 로그인 페이지/팝업 — 진행 중이면 LOGIN_IN_PROGRESS, 신규면 LOGIN_REQUIRED
        if prev_state in (LOGIN_ACTION_STARTED, LOGIN_IN_PROGRESS, LOGIN_REQUIRED):
            state = LOGIN_IN_PROGRESS
        else:
            state = LOGIN_REQUIRED
        reason = "auth_host" if is_auth_host else ("login_path" if is_login_path else "login_button")
    else:
        state = LOGIN_UNKNOWN
        reason = "no_strong_signal"

    return DetectionResult(
        state=state,
        reason=reason,
        is_auth_host=is_auth_host,
        is_account_picker=is_account_picker,
        has_logout_signal=has_logout,
        has_greeting=bool(greeting_user),
        sanitized_url=s_url,
        title=title_l,
        detected_user_hint=mask_email(greeting_user) if greeting_user else "",
        sub_signals=sub_signals,
    )
