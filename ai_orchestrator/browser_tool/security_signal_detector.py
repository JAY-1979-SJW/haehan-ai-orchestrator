"""
보안 신호 감지 모듈

서버 실행 중 로컬 전환이 필요한 신호를 공통으로 감지한다.

원칙:
- 신호 감지만 한다. 민감값을 수집·저장하지 않는다.
- password value 읽기 없음
- OTP value 읽기 없음
- cookie/session/token value 읽기 없음
- 인증서 파일 접근 없음
- 민감한 화면 텍스트 raw dump 없음
"""
from __future__ import annotations

from typing import Any

# ── 신호 상수 ──────────────────────────────────────────────────────────────────

SIG_LOGIN_REQUIRED = "login_required"
SIG_PASSWORD_INPUT = "password_input_detected"
SIG_CERT_AUTH = "cert_auth_detected"
SIG_OTP = "otp_detected"
SIG_CAPTCHA = "captcha_detected"
SIG_SECURITY_PROGRAM = "security_program_required"
SIG_BROWSER_UNSUPPORTED = "browser_unsupported"
SIG_BLOCKED_BY_SITE = "blocked_by_site"
SIG_HTTP_401 = "http_401"
SIG_HTTP_403 = "http_403"
SIG_REDIRECTED_TO_LOGIN = "redirected_to_login"
SIG_E_SIGNATURE = "e_signature_detected"
SIG_PAYMENT_OR_TRANSFER = "payment_or_transfer_detected"
SIG_BID_SUBMIT = "bid_submit_detected"
SIG_CONTRACT_SUBMIT = "contract_submit_detected"
SIG_FILE_DOWNLOAD = "file_download_detected"

_ALL_SIGNALS: frozenset[str] = frozenset({
    SIG_LOGIN_REQUIRED, SIG_PASSWORD_INPUT, SIG_CERT_AUTH, SIG_OTP,
    SIG_CAPTCHA, SIG_SECURITY_PROGRAM, SIG_BROWSER_UNSUPPORTED,
    SIG_BLOCKED_BY_SITE, SIG_HTTP_401, SIG_HTTP_403, SIG_REDIRECTED_TO_LOGIN,
    SIG_E_SIGNATURE, SIG_PAYMENT_OR_TRANSFER, SIG_BID_SUBMIT,
    SIG_CONTRACT_SUBMIT, SIG_FILE_DOWNLOAD,
})

# ── 신호 → 권장 실행 위치 ─────────────────────────────────────────────────────

_SIGNAL_TO_EXECUTION: dict[str, str] = {
    SIG_LOGIN_REQUIRED: "LOCAL_REQUIRED",
    SIG_PASSWORD_INPUT: "LOCAL_REQUIRED",
    SIG_CERT_AUTH: "LOCAL_REQUIRED",
    SIG_OTP: "USER_DIRECT_ONLY",
    SIG_CAPTCHA: "LOCAL_REQUIRED",
    SIG_SECURITY_PROGRAM: "LOCAL_REQUIRED",
    SIG_BROWSER_UNSUPPORTED: "LOCAL_REQUIRED",
    SIG_BLOCKED_BY_SITE: "LOCAL_REQUIRED",
    SIG_HTTP_401: "LOCAL_REQUIRED",
    SIG_HTTP_403: "LOCAL_REQUIRED",
    SIG_REDIRECTED_TO_LOGIN: "LOCAL_REQUIRED",
    SIG_E_SIGNATURE: "USER_DIRECT_ONLY",
    SIG_PAYMENT_OR_TRANSFER: "USER_DIRECT_ONLY",
    SIG_BID_SUBMIT: "USER_DIRECT_ONLY",
    SIG_CONTRACT_SUBMIT: "USER_DIRECT_ONLY",
    SIG_FILE_DOWNLOAD: "SERVER_FIRST",
}

# ── page title/url/body 감지 패턴 ─────────────────────────────────────────────

_LOGIN_PATTERNS: tuple[str, ...] = (
    "로그인", "login", "sign in", "signin",
    "인증", "authentication", "로그인이 필요", "please log in",
)
_CERT_PATTERNS: tuple[str, ...] = (
    "인증서", "certificate", "공인인증", "공동인증", "accredited certificate",
    "npki", "전자서명", "cert",
)
_OTP_PATTERNS: tuple[str, ...] = (
    "otp", "일회용 비밀번호", "보안카드", "security card", "보안코드",
)
_CAPTCHA_PATTERNS: tuple[str, ...] = (
    "captcha", "자동입력 방지", "보안문자", "recaptcha", "hcaptcha",
)
_SECURITY_PROGRAM_PATTERNS: tuple[str, ...] = (
    "보안프로그램", "security program", "iniwebkeyboard", "안전결제",
    "안전키보드", "키보드보안", "보안모듈",
)
_BROWSER_UNSUPPORTED_PATTERNS: tuple[str, ...] = (
    "지원하지 않는 브라우저", "internet explorer", "ie 전용",
    "크롬 브라우저를 사용", "browser not supported",
)
_BID_SUBMIT_PATTERNS: tuple[str, ...] = (
    "투찰", "입찰서 제출", "bid submit", "전자입찰",
)
_CONTRACT_PATTERNS: tuple[str, ...] = (
    "계약 체결", "계약서 제출", "contract submit",
)
_E_SIGN_PATTERNS: tuple[str, ...] = (
    "전자서명", "e-sign", "esign", "digital signature", "공인전자서명",
)
_PAYMENT_PATTERNS: tuple[str, ...] = (
    "결제", "payment", "송금", "transfer", "이체",
)


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(p in lower for p in patterns)


# 텍스트 패턴 → 신호 (감지/추가 순서 고정)
_TEXT_SIGNAL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (_LOGIN_PATTERNS, SIG_LOGIN_REQUIRED),
    (_CERT_PATTERNS, SIG_CERT_AUTH),
    (_OTP_PATTERNS, SIG_OTP),
    (_CAPTCHA_PATTERNS, SIG_CAPTCHA),
    (_SECURITY_PROGRAM_PATTERNS, SIG_SECURITY_PROGRAM),
    (_BROWSER_UNSUPPORTED_PATTERNS, SIG_BROWSER_UNSUPPORTED),
    (_BID_SUBMIT_PATTERNS, SIG_BID_SUBMIT),
    (_CONTRACT_PATTERNS, SIG_CONTRACT_SUBMIT),
    (_E_SIGN_PATTERNS, SIG_E_SIGNATURE),
    (_PAYMENT_PATTERNS, SIG_PAYMENT_OR_TRANSFER),
)


def detect_from_page_text(
    title: str = "",
    body_text: str = "",
    url: str = "",
    http_status: int = 200,
) -> dict[str, Any]:
    """
    페이지 text/url/http status에서 보안 신호를 감지한다.

    반환:
      has_security_signal, signals, recommended_execution,
      fallback_allowed, blocked_reason
    """
    signals: list[str] = []
    combined = f"{title}\n{body_text}"

    if http_status == 401:
        signals.append(SIG_HTTP_401)
    if http_status == 403:
        signals.append(SIG_HTTP_403)

    lower_url = (url or "").lower()
    if any(p in lower_url for p in ("login", "signin", "cert", "auth")):
        signals.append(SIG_REDIRECTED_TO_LOGIN)

    for patterns, signal in _TEXT_SIGNAL_RULES:
        if _match_any(combined, patterns):
            signals.append(signal)

    return _build_result(signals)


def detect_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    live runner / browser 결과 dict에서 보안 신호를 감지한다.
    민감값(password, OTP, cookie 값)은 읽지 않는다.
    """
    title = result.get("title") or ""
    body = result.get("body_text_sample") or ""
    url = result.get("final_url") or result.get("input_url") or ""
    http_status = int(result.get("http_status") or result.get("status_code") or 200)

    detected = detect_from_page_text(
        title=title, body_text=body, url=url, http_status=http_status
    )

    # 추가: explicit signal 필드 (live runner가 직접 설정한 경우)
    explicit: list[str] = result.get("security_signals") or []
    for sig in explicit:
        if sig in _ALL_SIGNALS and sig not in detected["signals"]:
            detected["signals"].append(sig)

    return _build_result(detected["signals"])


def classify_signals(signals: list[str]) -> dict[str, Any]:
    """신호 목록을 권장 실행 위치로 분류한다."""
    return _build_result(signals)


def _build_result(signals: list[str]) -> dict[str, Any]:
    unique = list(dict.fromkeys(signals))
    if not unique:
        return {
            "has_security_signal": False,
            "signals": [],
            "recommended_execution": "SERVER_FIRST",
            "fallback_allowed": True,
            "blocked_reason": None,
        }

    # 우선순위: BLOCKED > USER_DIRECT_ONLY > LOCAL_REQUIRED > SERVER_FIRST
    priorities = {
        "BLOCKED": 4, "USER_DIRECT_ONLY": 3,
        "LOCAL_REQUIRED": 2, "SERVER_FIRST": 1,
    }
    recommended = "SERVER_FIRST"
    for sig in unique:
        loc = _SIGNAL_TO_EXECUTION.get(sig, "LOCAL_REQUIRED")
        if priorities.get(loc, 0) > priorities.get(recommended, 0):
            recommended = loc

    fallback_allowed = recommended not in ("BLOCKED", "USER_DIRECT_ONLY")
    blocked_reason = None
    if recommended == "BLOCKED":
        blocked_reason = f"차단 신호 감지: {unique}"

    return {
        "has_security_signal": True,
        "signals": unique,
        "recommended_execution": recommended,
        "fallback_allowed": fallback_allowed,
        "blocked_reason": blocked_reason,
    }
