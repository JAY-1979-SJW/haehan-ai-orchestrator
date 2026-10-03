"""
G2B 도메인 정규화 정책

g2b.go.kr / www.g2b.go.kr 공개 read-only 경로를 정규화하고
로그인/입찰/제출/계약/결제/인증서 경로는 차단한다.

원칙:
- safe_to_execute 항상 False
- download_auto_allowed 항상 False
- wildcard *.g2b.go.kr 허용 없음
- type/submit/fill/click_submit operation 차단
- 쿠키/session/token 추출 코드 없음
- DB write 없음
- task_executor/browser_worker 연결 없음
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ── G2B 공개 허용 도메인 ───────────────────────────────────────────────────────

_G2B_APEX_DOMAIN = "g2b.go.kr"

_G2B_PUBLIC_READONLY_DOMAINS: frozenset[str] = frozenset(
    {
        "g2b.go.kr",
        "www.g2b.go.kr",
    }
)

# www prefix → apex로 정규화
_G2B_WWW_NORMALIZE_MAP: dict[str, str] = {
    "www.g2b.go.kr": "g2b.go.kr",
}

# 검증 필요 서브도메인 (공개 read-only 확인 전)
_G2B_READONLY_CANDIDATE_DOMAINS: frozenset[str] = frozenset(
    {
        "shop.g2b.go.kr",
    }
)

# ── domain_decision 값 ────────────────────────────────────────────────────────

DOMAIN_G2B_PUBLIC_READONLY = "G2B_PUBLIC_READONLY"
DOMAIN_READONLY_CANDIDATE = "READONLY_CANDIDATE"
DOMAIN_NEEDS_URL_VERIFICATION = "NEEDS_URL_VERIFICATION"
DOMAIN_NOT_G2B = "NOT_G2B"

# ── path_decision 값 ─────────────────────────────────────────────────────────

PATH_READONLY_ALLOWED = "PATH_READONLY_ALLOWED"
PATH_DOWNLOAD_MANUAL_ONLY = "PATH_DOWNLOAD_MANUAL_ONLY"
PATH_BLOCKED_LOGIN = "PATH_BLOCKED_LOGIN"
PATH_BLOCKED_CERT = "PATH_BLOCKED_CERT"
PATH_BLOCKED_BID_SUBMIT = "PATH_BLOCKED_BID_SUBMIT"
PATH_BLOCKED_CONTRACT = "PATH_BLOCKED_CONTRACT"
PATH_BLOCKED_PAYMENT = "PATH_BLOCKED_PAYMENT"
PATH_UNKNOWN = "PATH_UNKNOWN"

# ── 금지 경로 키워드 (소문자 경로 부분문자열 매칭) ────────────────────────────

_LOGIN_PATH_KEYWORDS: frozenset[str] = frozenset(
    {
        "egovuserreqstlogin",
        "login",
        "/co/menu/",
        "userlogin",
        "signin",
    }
)

_CERT_PATH_KEYWORDS: frozenset[str] = frozenset(
    {
        "/cert",
        "/certificate",
        "/sign",
        "/esign",
        "/nksign",
    }
)

_BID_SUBMIT_PATH_KEYWORDS: frozenset[str] = frozenset(
    {
        "/bid/",
        "/bidding/",
        "/submit",
        "/apply",
        "/ptb05",
    }
)

_CONTRACT_PATH_KEYWORDS: frozenset[str] = frozenset(
    {
        "/contract",
        "/ct/menu/ntn02",
        "/ctb",
    }
)

_PAYMENT_PATH_KEYWORDS: frozenset[str] = frozenset(
    {
        "/pay",
        "/payment",
        "/checkout",
    }
)

# ── 금지 operation ────────────────────────────────────────────────────────────

_BLOCKED_OPERATIONS: frozenset[str] = frozenset(
    {
        "submit",
        "type",
        "fill",
        "click_submit",
        "auto_login",
        "execute_type",
        "execute_submit",
        "download",
    }
)

# click은 별도 승인 필요 (차단이 아닌 requires_approval)
_APPROVAL_REQUIRED_OPERATIONS: frozenset[str] = frozenset(
    {
        "click",
    }
)

# 허용 operation
_READONLY_OPERATIONS: frozenset[str] = frozenset(
    {
        "read",
        "navigate",
        "open_url",
    }
)


def normalize_g2b_domain(domain: str) -> dict[str, Any]:
    """
    G2B 도메인을 정규화한다.

    반환:
    - original_domain
    - normalized_domain
    - domain_decision
    - is_g2b_public_readonly
    - needs_url_verification
    - safe_to_execute (False)
    """
    d = (domain or "").lower().strip()

    if not d:
        return {
            "original_domain": domain,
            "normalized_domain": "",
            "domain_decision": DOMAIN_NOT_G2B,
            "is_g2b_public_readonly": False,
            "needs_url_verification": False,
            "safe_to_execute": False,
            "message_ko": "도메인 없음.",
        }

    # www.g2b.go.kr → g2b.go.kr 정규화
    normalized = _G2B_WWW_NORMALIZE_MAP.get(d, d)

    if d in _G2B_PUBLIC_READONLY_DOMAINS:
        return {
            "original_domain": domain,
            "normalized_domain": normalized,
            "domain_decision": DOMAIN_G2B_PUBLIC_READONLY,
            "is_g2b_public_readonly": True,
            "needs_url_verification": False,
            "safe_to_execute": False,
            "message_ko": f"{d} → {normalized} 정규화. G2B 공개 read-only 허용 도메인.",
        }

    if d in _G2B_READONLY_CANDIDATE_DOMAINS:
        return {
            "original_domain": domain,
            "normalized_domain": d,
            "domain_decision": DOMAIN_READONLY_CANDIDATE,
            "is_g2b_public_readonly": False,
            "needs_url_verification": True,
            "safe_to_execute": False,
            "message_ko": f"{d}: 공개 read-only 후보. URL 검증 필요.",
        }

    # *.g2b.go.kr 미확인 서브도메인
    if d.endswith(".g2b.go.kr") or d == "g2b.go.kr":
        return {
            "original_domain": domain,
            "normalized_domain": d,
            "domain_decision": DOMAIN_NEEDS_URL_VERIFICATION,
            "is_g2b_public_readonly": False,
            "needs_url_verification": True,
            "safe_to_execute": False,
            "message_ko": f"{d}: 미확인 G2B 서브도메인. URL 검증 필요.",
        }

    return {
        "original_domain": domain,
        "normalized_domain": d,
        "domain_decision": DOMAIN_NOT_G2B,
        "is_g2b_public_readonly": False,
        "needs_url_verification": False,
        "safe_to_execute": False,
        "message_ko": f"{d}: G2B 도메인 아님.",
    }


def _classify_path(path: str) -> str:
    p = path.lower()

    # 판정 우선순위 순서 고정 (앞쪽이 먼저 차단)
    for keywords, decision in (
        (_LOGIN_PATH_KEYWORDS, PATH_BLOCKED_LOGIN),
        (_CERT_PATH_KEYWORDS, PATH_BLOCKED_CERT),
        (_BID_SUBMIT_PATH_KEYWORDS, PATH_BLOCKED_BID_SUBMIT),
        (_CONTRACT_PATH_KEYWORDS, PATH_BLOCKED_CONTRACT),
        (_PAYMENT_PATH_KEYWORDS, PATH_BLOCKED_PAYMENT),
    ):
        if any(kw in p for kw in keywords):
            return decision

    return PATH_READONLY_ALLOWED


def classify_g2b_url(
    url: str,
    operation_type: str | None = None,
) -> dict[str, Any]:
    """
    G2B URL을 분류한다.

    반환:
    - normalized_domain
    - domain_decision
    - path_decision
    - readonly_allowed
    - download_auto_allowed (항상 False)
    - blocked_reason
    - needs_url_verification
    - operation_decision
    - requires_approval
    - safe_to_dispatch
    - safe_to_execute (항상 False)
    - message_ko
    """
    result: dict[str, Any] = {
        "original_url": url,
        "normalized_domain": "",
        "domain_decision": DOMAIN_NOT_G2B,
        "path_decision": PATH_UNKNOWN,
        "readonly_allowed": False,
        "download_auto_allowed": False,
        "blocked_reason": "",
        "needs_url_verification": False,
        "operation_decision": "ALLOW",
        "requires_approval": False,
        "safe_to_dispatch": False,
        "safe_to_execute": False,
        "message_ko": "",
    }

    op = (operation_type or "").lower().strip()

    # operation 사전 차단
    if op in _BLOCKED_OPERATIONS:
        result["operation_decision"] = "BLOCKED"
        result["blocked_reason"] = f"OPERATION_BLOCKED: {op}"
        result["message_ko"] = f"operation '{op}'은 G2B에서 허용되지 않습니다."
        if op == "download":
            result["path_decision"] = PATH_DOWNLOAD_MANUAL_ONLY
        return result

    if op in _APPROVAL_REQUIRED_OPERATIONS:
        result["operation_decision"] = "REQUIRES_APPROVAL"
        result["requires_approval"] = True

    # URL 파싱
    try:
        parsed = urlparse(url) if url else None
        domain = parsed.netloc if parsed else ""
        path = parsed.path if parsed else ""
    except Exception as exc:  # noqa: BLE001 - classify_g2b_url(): URL 파싱 실패 시 blocked_reason=URL_PARSE_ERROR로 설정 후 반환 — 결과 dict의 safe_to_dispatch/safe_to_execute/readonly_allowed는 초기값 False 그대로 유지되어 fail-closed
        logger.warning("G2B URL 분류(URL 파싱) 실패: %s", type(exc).__name__)
        result["blocked_reason"] = "URL_PARSE_ERROR"
        result["message_ko"] = "URL 파싱 오류."
        return result

    # 도메인 정규화
    domain_info = normalize_g2b_domain(domain)
    result["normalized_domain"] = domain_info["normalized_domain"]
    result["domain_decision"] = domain_info["domain_decision"]
    result["needs_url_verification"] = domain_info["needs_url_verification"]

    if domain_info["domain_decision"] == DOMAIN_NOT_G2B:
        result["blocked_reason"] = "NOT_G2B_DOMAIN"
        result["message_ko"] = domain_info["message_ko"]
        return result

    if domain_info["domain_decision"] in (DOMAIN_NEEDS_URL_VERIFICATION, DOMAIN_READONLY_CANDIDATE):
        result["blocked_reason"] = "NEEDS_URL_VERIFICATION"
        result["message_ko"] = domain_info["message_ko"]
        return result

    # 경로 분류
    path_decision = _classify_path(path)
    result["path_decision"] = path_decision

    blocked_paths = {
        PATH_BLOCKED_LOGIN,
        PATH_BLOCKED_CERT,
        PATH_BLOCKED_BID_SUBMIT,
        PATH_BLOCKED_CONTRACT,
        PATH_BLOCKED_PAYMENT,
    }

    if path_decision in blocked_paths:
        result["blocked_reason"] = f"PATH_BLOCKED: {path_decision}"
        result["operation_decision"] = "BLOCKED"
        result["message_ko"] = f"경로 '{path}': {path_decision}"
        return result

    # 공개 read-only 허용
    if path_decision == PATH_READONLY_ALLOWED and op in _READONLY_OPERATIONS | {""}:
        result["readonly_allowed"] = True
        result["safe_to_dispatch"] = True
        result["message_ko"] = "G2B 공개 read-only 경로. 허용."
        return result

    result["message_ko"] = f"G2B 경로 분류: {path_decision}, operation: {op}"
    return result


def is_g2b_readonly_allowed(url: str) -> bool:
    """URL이 G2B 공개 read-only 허용 대상인지 반환한다."""
    result = classify_g2b_url(url, operation_type="read")
    return result.get("readonly_allowed", False)


def validate_g2b_domain_policy_result(result: dict[str, Any]) -> list[str]:
    """G2B 도메인 정책 결과의 필수 필드 및 정책 준수를 검증한다."""
    errors: list[str] = []

    required = [
        "domain_decision",
        "path_decision",
        "readonly_allowed",
        "download_auto_allowed",
        "safe_to_execute",
    ]
    for field in required:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    if result.get("download_auto_allowed") is not False:
        errors.append("download_auto_allowed는 항상 False여야 한다")

    valid_domain_decisions = {
        DOMAIN_G2B_PUBLIC_READONLY,
        DOMAIN_READONLY_CANDIDATE,
        DOMAIN_NEEDS_URL_VERIFICATION,
        DOMAIN_NOT_G2B,
    }
    if "domain_decision" in result and result["domain_decision"] not in valid_domain_decisions:
        errors.append(f"유효하지 않은 domain_decision: {result['domain_decision']}")

    return errors


__all__ = [
    "DOMAIN_G2B_PUBLIC_READONLY",
    "DOMAIN_NEEDS_URL_VERIFICATION",
    "DOMAIN_NOT_G2B",
    "DOMAIN_READONLY_CANDIDATE",
    "PATH_BLOCKED_BID_SUBMIT",
    "PATH_BLOCKED_CERT",
    "PATH_BLOCKED_CONTRACT",
    "PATH_BLOCKED_LOGIN",
    "PATH_BLOCKED_PAYMENT",
    "PATH_DOWNLOAD_MANUAL_ONLY",
    "PATH_READONLY_ALLOWED",
    "classify_g2b_url",
    "is_g2b_readonly_allowed",
    "normalize_g2b_domain",
    "validate_g2b_domain_policy_result",
]
