"""
서버 브라우저 경계 정책

제한 사이트(은행/카드/세무/정부/보험/인증서/Google 계정)는
서버 브라우저에서 절대 접속 금지.
로컬 Agent 또는 공식 API/OAuth 경로만 허용.

safe_to_execute 항상 False.
click/type/fill/submit 코드 없음.
cookie/session/token 추출 없음.
"""

from __future__ import annotations

from typing import Any

# ── server_browser_decision 값 ────────────────────────────────────────────────

DECISION_SERVER_BROWSER_ALLOWED_READONLY = "SERVER_BROWSER_ALLOWED_READONLY"
DECISION_REQUIRE_LOCAL_AGENT = "REQUIRE_LOCAL_AGENT"
DECISION_REQUIRE_API_CONNECTOR = "REQUIRE_API_CONNECTOR"
DECISION_REQUIRE_USER_PRESENT = "REQUIRE_USER_PRESENT"
DECISION_BLOCK = "BLOCK"

# ── 실행 위치 ─────────────────────────────────────────────────────────────────

EXEC_LOC_SERVER_BROWSER = "SERVER_BROWSER"
EXEC_LOC_LOCAL_AGENT = "LOCAL_AGENT"
EXEC_LOC_API = "API_ONLY"
EXEC_LOC_USER_PRESENT = "USER_PRESENT_ONLY"
EXEC_LOC_BLOCKED = "BLOCKED"

# ── 서버 브라우저 접속 금지 카테고리 ─────────────────────────────────────────

_SERVER_BROWSER_FORBIDDEN_CATEGORIES: frozenset[str] = frozenset({
    "bank",
    "card",
    "tax",
    "hometax",
    "government",
    "gov24",
    "insurance",
    "four_insurance",
    "certificate",
    "certificate_portal",
    "financial_certificate",
})

# Google 계정은 BLOCK, 나머지 Google 서비스는 API 필요
_GOOGLE_ACCOUNTS_KEYWORDS: frozenset[str] = frozenset({
    "accounts.google.com",
    "google.com/accounts",
    "google.com/signin",
    "google.com/login",
})

_GOOGLE_SERVICE_CATEGORIES: frozenset[str] = frozenset({
    "google",
    "google_workspace",
    "gmail",
    "google_drive",
    "google_calendar",
    "google_docs",
    "google_sheets",
    "cloud_service",
})

# G2B 공개 read-only만 서버 브라우저 허용
_SERVER_BROWSER_ALLOWED_READONLY_CATEGORIES: frozenset[str] = frozenset({
    "g2b_public_readonly",
    "g2b",
    "public_readonly",
})

# 서버 브라우저 접속 금지 요구사항
_REQUIRES_LOCAL_AGENT_FLAGS: frozenset[str] = frozenset({
    "requires_certificate",
    "requires_financial_certificate",
    "requires_otp",
    "requires_password",
    "requires_security_plugin",
    "requires_captcha",
    "user_present_required",
    "local_agent_required",
})


def classify_restricted_site_for_server_browser(payload: dict[str, Any]) -> dict[str, Any]:
    """
    사이트가 서버 브라우저 접속 금지 대상인지 분류한다.

    반환:
    - server_browser_decision
    - execution_location_required
    - server_browser_allowed (bool)
    - restriction_categories (list)
    - safe_to_execute (False)
    """
    site_category = (payload.get("site_category") or "").lower()
    target_domain = (payload.get("target_domain") or "").lower()
    target_url = (payload.get("target_url") or "").lower()

    restriction_categories: list[str] = []

    # Google accounts 도메인 → BLOCK (서버 브라우저 로그인 금지)
    if any(kw in target_domain or kw in target_url for kw in _GOOGLE_ACCOUNTS_KEYWORDS):
        restriction_categories.append("google_accounts_login")
        return {
            "server_browser_decision": DECISION_BLOCK,
            "execution_location_required": EXEC_LOC_BLOCKED,
            "server_browser_allowed": False,
            "restriction_categories": restriction_categories,
            "block_reason": "Google 계정 로그인은 서버 브라우저 금지. OAuth API만 허용.",
            "safe_to_execute": False,
        }

    # Google 서비스 카테고리 → API 필요
    if site_category in _GOOGLE_SERVICE_CATEGORIES:
        restriction_categories.append("google_service")
        return {
            "server_browser_decision": DECISION_REQUIRE_API_CONNECTOR,
            "execution_location_required": EXEC_LOC_API,
            "server_browser_allowed": False,
            "restriction_categories": restriction_categories,
            "block_reason": "Google 서비스는 공식 API/OAuth만 허용.",
            "safe_to_execute": False,
        }

    # 제한 카테고리 → 로컬 Agent 또는 user-present
    if site_category in _SERVER_BROWSER_FORBIDDEN_CATEGORIES:
        restriction_categories.append(f"restricted_category:{site_category}")

    # 요구사항 플래그 확인
    for flag in _REQUIRES_LOCAL_AGENT_FLAGS:
        if payload.get(flag) is True:
            restriction_categories.append(flag)

    if restriction_categories:
        # 인증서/OTP/비밀번호 요구 → user-present
        auth_flags = {"requires_certificate", "requires_financial_certificate",
                      "requires_otp", "requires_password", "user_present_required"}
        if any(f in restriction_categories for f in auth_flags):
            return {
                "server_browser_decision": DECISION_REQUIRE_USER_PRESENT,
                "execution_location_required": EXEC_LOC_USER_PRESENT,
                "server_browser_allowed": False,
                "restriction_categories": restriction_categories,
                "block_reason": "사용자 직접 인증 필요. 서버 브라우저 금지.",
                "safe_to_execute": False,
            }
        # CAPTCHA → BLOCK
        if "requires_captcha" in restriction_categories:
            return {
                "server_browser_decision": DECISION_BLOCK,
                "execution_location_required": EXEC_LOC_BLOCKED,
                "server_browser_allowed": False,
                "restriction_categories": restriction_categories,
                "block_reason": "CAPTCHA 요구 사이트. 자동화 차단.",
                "safe_to_execute": False,
            }
        # 나머지 제한 카테고리 → 로컬 Agent
        return {
            "server_browser_decision": DECISION_REQUIRE_LOCAL_AGENT,
            "execution_location_required": EXEC_LOC_LOCAL_AGENT,
            "server_browser_allowed": False,
            "restriction_categories": restriction_categories,
            "block_reason": "제한 사이트. 로컬 Agent 전용.",
            "safe_to_execute": False,
        }

    # G2B 공개 read-only → 서버 브라우저 허용
    if site_category in _SERVER_BROWSER_ALLOWED_READONLY_CATEGORIES:
        return {
            "server_browser_decision": DECISION_SERVER_BROWSER_ALLOWED_READONLY,
            "execution_location_required": EXEC_LOC_SERVER_BROWSER,
            "server_browser_allowed": True,
            "restriction_categories": [],
            "block_reason": "",
            "safe_to_execute": False,
        }

    # 분류 불명 → 로컬 Agent 기본
    return {
        "server_browser_decision": DECISION_REQUIRE_LOCAL_AGENT,
        "execution_location_required": EXEC_LOC_LOCAL_AGENT,
        "server_browser_allowed": False,
        "restriction_categories": ["unknown_site_category"],
        "block_reason": "분류되지 않은 사이트. 로컬 Agent 기본 처리.",
        "safe_to_execute": False,
    }


def evaluate_server_browser_allowed(payload: dict[str, Any]) -> dict[str, Any]:
    """
    서버 브라우저 허용 여부를 종합 판정한다.

    site_compliance_policy/site_access_compatibility_auditor와 충돌 없이
    추가 경계 검사를 수행한다.
    """
    classification = classify_restricted_site_for_server_browser(payload)

    execution_location = payload.get("execution_location") or ""
    requested_runtime = payload.get("requested_runtime") or ""

    # 서버 브라우저로 요청했으나 금지된 경우 강제 차단
    if execution_location == "server_browser" or requested_runtime == "server_playwright":
        if not classification["server_browser_allowed"]:
            classification["server_browser_decision"] = DECISION_BLOCK
            classification["execution_location_required"] = EXEC_LOC_BLOCKED
            classification["block_reason"] = (
                f"요청된 실행 위치가 server_browser이나 정책상 금지된 사이트입니다. "
                f"원래 이유: {classification.get('block_reason', '')}"
            )

    message_ko = _build_message_ko(classification)
    classification["message_ko"] = message_ko
    classification["safe_to_execute"] = False
    classification["safe_to_dispatch"] = False

    return classification


def _build_message_ko(result: dict[str, Any]) -> str:
    decision = result.get("server_browser_decision", "")
    if decision == DECISION_SERVER_BROWSER_ALLOWED_READONLY:
        return "공개 read-only 페이지로 서버 브라우저 접근이 허용됩니다."
    if decision == DECISION_REQUIRE_LOCAL_AGENT:
        return "이 사이트는 사용자 PC 로컬 Agent에서만 접근 가능합니다."
    if decision == DECISION_REQUIRE_API_CONNECTOR:
        return "공식 API/OAuth 경로를 사용해야 합니다. 서버 브라우저 접근 금지."
    if decision == DECISION_REQUIRE_USER_PRESENT:
        return "사용자가 직접 인증을 완료해야 합니다. 서버 브라우저 금지."
    if decision == DECISION_BLOCK:
        return "이 사이트는 자동화 접근이 완전히 차단됩니다."
    return "서버 브라우저 접근 정책을 확인할 수 없습니다."


def validate_server_browser_boundary_result(result: dict[str, Any]) -> list[str]:
    """경계 판정 결과의 필수 필드 및 정책 준수를 검증한다."""
    errors: list[str] = []
    required = [
        "server_browser_decision", "execution_location_required",
        "server_browser_allowed", "safe_to_execute",
    ]
    for field in required:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    valid_decisions = {
        DECISION_SERVER_BROWSER_ALLOWED_READONLY,
        DECISION_REQUIRE_LOCAL_AGENT,
        DECISION_REQUIRE_API_CONNECTOR,
        DECISION_REQUIRE_USER_PRESENT,
        DECISION_BLOCK,
    }
    if result.get("server_browser_decision") not in valid_decisions:
        errors.append(f"유효하지 않은 server_browser_decision: {result.get('server_browser_decision')}")

    return errors
