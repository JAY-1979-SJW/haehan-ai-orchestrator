"""
Browser Engine Capability Classifier

사이트별로 어떤 실행 엔진을 사용할 수 있는지 분류한다.
무조건 Playwright 먼저 시도하는 구조를 금지하고,
정책 기반으로 엔진을 라우팅한다.

safe_to_execute: 항상 False.
click/type/fill/submit 코드 없음.
cookie/session/token 추출 없음.
인증서 비밀번호/OTP 입력 코드 없음.
"""

from __future__ import annotations

from typing import Any

# ── Engine Capability 값 ──────────────────────────────────────────────────────

ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED = "SERVER_PLAYWRIGHT_READONLY_ALLOWED"
ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED = "LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED"
ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED = "LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED"
ENGINE_API_CONNECTOR_REQUIRED = "API_CONNECTOR_REQUIRED"
ENGINE_AUTOMATION_BLOCKED = "AUTOMATION_BLOCKED"
ENGINE_NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW"

# ── recommended_route 값 ──────────────────────────────────────────────────────

ROUTE_SERVER_PLAYWRIGHT_READONLY = "SERVER_PLAYWRIGHT_READONLY"
ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY = "LOCAL_AGENT_PLAYWRIGHT_READONLY"
ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT = "LOCAL_SYSTEM_BROWSER_USER_PRESENT"
ROUTE_API_CONNECTOR = "API_CONNECTOR"
ROUTE_BLOCK = "BLOCK"
ROUTE_MANUAL_REVIEW = "MANUAL_REVIEW"

# ── 서버 Playwright 허용 URL (완전 일치) ──────────────────────────────────────

_SERVER_PLAYWRIGHT_ALLOWED_URLS: frozenset[str] = frozenset({
    "about:blank",
    "",
    "https://example.com",
    "https://example.com/",
})

# ── 서버 Playwright 허용 URL prefix ──────────────────────────────────────────

_SERVER_PLAYWRIGHT_ALLOWED_PREFIXES: tuple[str, ...] = ("data:text/html",)

# ── 서버 Playwright 허용 사이트 카테고리 ─────────────────────────────────────

_SERVER_PLAYWRIGHT_ALLOWED_CATEGORIES: frozenset[str] = frozenset({
    "g2b_public_readonly",
    "g2b",
    "public_readonly",
    "test_page",
    "example",
})

# ── Google accounts → BLOCK ───────────────────────────────────────────────────

_GOOGLE_ACCOUNTS_DOMAINS: frozenset[str] = frozenset({
    "accounts.google.com",
})

# ── Google 서비스 → API_CONNECTOR ─────────────────────────────────────────────

_GOOGLE_SERVICE_DOMAINS: frozenset[str] = frozenset({
    "mail.google.com",
    "drive.google.com",
    "calendar.google.com",
    "docs.google.com",
    "sheets.google.com",
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

# ── 로컬 user-present 필요 사이트 카테고리 ────────────────────────────────────

_USER_PRESENT_CATEGORIES: frozenset[str] = frozenset({
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

# ── user-present 필요 인증 플래그 ─────────────────────────────────────────────

_USER_PRESENT_FLAGS: frozenset[str] = frozenset({
    "requires_certificate",
    "requires_financial_certificate",
    "requires_otp",
    "requires_password",
    "user_present_required",
})

# ── 자동화 차단 플래그 ────────────────────────────────────────────────────────

_AUTOMATION_BLOCK_FLAGS: frozenset[str] = frozenset({
    "requires_captcha",
})


def _server_readonly_result(message_ko: str) -> dict[str, Any]:
    """서버 Playwright read-only 허용 결과 (세 허용 분기 공통)."""
    return _make_result(
        engine_capability=ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED,
        recommended_route=ROUTE_SERVER_PLAYWRIGHT_READONLY,
        server_playwright_allowed=True,
        fallback_allowed=True,
        fallback_route=ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY,
        block_reason="",
        message_ko=message_ko,
    )


def _classify_google(
    site_category: str, target_domain: str, target_url: str
) -> dict[str, Any] | None:
    """Google 계정/서비스 관련 분류. 해당 없으면 None (판정 순서 유지)."""
    # Google accounts → BLOCK
    if target_domain in _GOOGLE_ACCOUNTS_DOMAINS or any(
        kw in target_url for kw in ("accounts.google.com", "google.com/accounts",
                                     "google.com/signin", "google.com/login")
    ):
        return _make_result(
            engine_capability=ENGINE_AUTOMATION_BLOCKED,
            recommended_route=ROUTE_BLOCK,
            server_playwright_allowed=False,
            local_agent_playwright_allowed=False,
            block_reason="Google 계정 로그인 페이지. 서버/로컬 Playwright 금지. OAuth만 허용.",
            message_ko="Google 계정 로그인은 자동화가 차단됩니다. OAuth API를 사용하세요.",
        )

    # Google 서비스 도메인 → API_CONNECTOR
    if target_domain in _GOOGLE_SERVICE_DOMAINS:
        return _make_result(
            engine_capability=ENGINE_API_CONNECTOR_REQUIRED,
            recommended_route=ROUTE_API_CONNECTOR,
            api_connector_required=True,
            block_reason="Google 서비스. 공식 API/OAuth만 허용.",
            message_ko="Google 서비스는 공식 API/OAuth를 사용해야 합니다. 브라우저 자동화 차단.",
        )

    # Google 서비스 카테고리 → API_CONNECTOR
    if site_category in _GOOGLE_SERVICE_CATEGORIES:
        return _make_result(
            engine_capability=ENGINE_API_CONNECTOR_REQUIRED,
            recommended_route=ROUTE_API_CONNECTOR,
            api_connector_required=True,
            block_reason="Google 서비스 카테고리. 공식 API/OAuth만 허용.",
            message_ko="Google 서비스는 공식 API/OAuth를 사용해야 합니다.",
        )
    return None


def classify_browser_engine_capability(payload: dict[str, Any]) -> dict[str, Any]:
    """
    사이트별 브라우저 엔진 실행 가능 여부를 분류한다.

    입력 필드:
    - site_category, target_domain, target_url
    - operation_type, action_name
    - auth_methods, requires_certificate, requires_financial_certificate
    - requires_otp, requires_password, requires_captcha
    - requires_security_plugin, blocks_remote_access
    - official_api_available, oauth_available
    - user_present_required, local_agent_required
    - production_mode

    반환 필드:
    - engine_capability, recommended_route
    - server_playwright_allowed, local_agent_playwright_allowed
    - local_system_browser_required, api_connector_required
    - user_present_required, automation_blocked
    - fallback_allowed, fallback_route
    - block_reason, safe_to_dispatch, safe_to_execute
    - message_ko
    """
    site_category = (payload.get("site_category") or "").lower()
    target_domain = (payload.get("target_domain") or "").lower()
    target_url = (payload.get("target_url") or "").lower()

    # production_mode → BLOCK
    if payload.get("production_mode") is True:
        return _make_result(
            engine_capability=ENGINE_AUTOMATION_BLOCKED,
            recommended_route=ROUTE_BLOCK,
            block_reason="production_mode=true: 엔진 실행 차단.",
            message_ko="production_mode=true: 모든 브라우저 엔진 실행 차단.",
        )

    # CAPTCHA → AUTOMATION_BLOCKED
    if payload.get("requires_captcha") is True:
        return _make_result(
            engine_capability=ENGINE_AUTOMATION_BLOCKED,
            recommended_route=ROUTE_BLOCK,
            block_reason="requires_captcha: CAPTCHA 요구 사이트. 자동화 차단.",
            message_ko="CAPTCHA 필요 사이트입니다. 자동화가 차단됩니다.",
        )

    google_result = _classify_google(site_category, target_domain, target_url)
    if google_result is not None:
        return google_result

    # user-present 인증 플래그 → LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    for flag in _USER_PRESENT_FLAGS:
        if payload.get(flag) is True:
            return _make_result(
                engine_capability=ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
                recommended_route=ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
                local_system_browser_required=True,
                user_present_required=True,
                block_reason=f"{flag}: 사용자 직접 인증 필요. 서버/로컬 Playwright 금지.",
                message_ko=f"{flag}: 사용자 직접 인증이 필요합니다. 기본 브라우저를 사용하세요.",
            )

    # user-present 카테고리 → LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED
    if site_category in _USER_PRESENT_CATEGORIES:
        return _make_result(
            engine_capability=ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
            recommended_route=ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
            local_system_browser_required=True,
            user_present_required=True,
            block_reason=f"제한 카테고리({site_category}). 서버/로컬 Playwright 금지.",
            message_ko=f"{site_category} 사이트입니다. 사용자 직접 브라우저 접근이 필요합니다.",
        )

    # 서버 Playwright 허용 URL
    if (
        not target_url
        or target_url in _SERVER_PLAYWRIGHT_ALLOWED_URLS
        or any(target_url.startswith(p) for p in _SERVER_PLAYWRIGHT_ALLOWED_PREFIXES)
    ):
        return _server_readonly_result("서버 Playwright read-only 접근이 허용됩니다.")

    # 서버 Playwright 허용 카테고리
    if site_category in _SERVER_PLAYWRIGHT_ALLOWED_CATEGORIES:
        return _server_readonly_result(f"{site_category} 카테고리. 서버 Playwright read-only 허용.")

    # example.com 도메인
    if target_domain in ("example.com", "www.example.com"):
        return _server_readonly_result("example.com: 서버 Playwright read-only 허용.")

    # 알 수 없는 사이트 → NEEDS_MANUAL_REVIEW
    return _make_result(
        engine_capability=ENGINE_NEEDS_MANUAL_REVIEW,
        recommended_route=ROUTE_MANUAL_REVIEW,
        block_reason="미분류 사이트. 수동 실사 및 사용자 승인 필요.",
        message_ko="알 수 없는 사이트입니다. 수동 실사 후 사용자 승인이 필요합니다.",
    )


def get_recommended_execution_route(payload: dict[str, Any]) -> dict[str, Any]:
    """
    분류 결과에서 recommended_route와 실행 가능 여부를 반환한다.
    """
    result = classify_browser_engine_capability(payload)
    return {
        "recommended_route": result["recommended_route"],
        "server_playwright_allowed": result["server_playwright_allowed"],
        "local_agent_playwright_allowed": result["local_agent_playwright_allowed"],
        "local_system_browser_required": result["local_system_browser_required"],
        "api_connector_required": result["api_connector_required"],
        "user_present_required": result["user_present_required"],
        "automation_blocked": result["automation_blocked"],
        "fallback_allowed": result["fallback_allowed"],
        "fallback_route": result["fallback_route"],
        "safe_to_dispatch": result["safe_to_dispatch"],
        "safe_to_execute": False,
        "block_reason": result["block_reason"],
        "message_ko": result["message_ko"],
    }


def validate_engine_capability_result(result: dict[str, Any]) -> list[str]:
    """
    분류 결과의 필수 필드 및 정책 준수를 검증한다.
    """
    errors: list[str] = []

    required_fields = [
        "engine_capability", "recommended_route",
        "server_playwright_allowed", "local_agent_playwright_allowed",
        "local_system_browser_required", "api_connector_required",
        "user_present_required", "automation_blocked",
        "fallback_allowed", "safe_to_dispatch", "safe_to_execute",
        "block_reason", "message_ko",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("safe_to_execute") is not False:
        errors.append("safe_to_execute는 항상 False여야 한다")

    valid_capabilities = {
        ENGINE_SERVER_PLAYWRIGHT_READONLY_ALLOWED,
        ENGINE_LOCAL_AGENT_PLAYWRIGHT_READONLY_ALLOWED,
        ENGINE_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED,
        ENGINE_API_CONNECTOR_REQUIRED,
        ENGINE_AUTOMATION_BLOCKED,
        ENGINE_NEEDS_MANUAL_REVIEW,
    }
    if result.get("engine_capability") not in valid_capabilities:
        errors.append(f"유효하지 않은 engine_capability: {result.get('engine_capability')}")

    valid_routes = {
        ROUTE_SERVER_PLAYWRIGHT_READONLY,
        ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY,
        ROUTE_LOCAL_SYSTEM_BROWSER_USER_PRESENT,
        ROUTE_API_CONNECTOR,
        ROUTE_BLOCK,
        ROUTE_MANUAL_REVIEW,
    }
    if result.get("recommended_route") not in valid_routes:
        errors.append(f"유효하지 않은 recommended_route: {result.get('recommended_route')}")

    return errors


def _make_result(  # noqa: PLR0913 - 내부 결과 dict 생성 헬퍼, 필드 나열형
    engine_capability: str,
    recommended_route: str,
    server_playwright_allowed: bool = False,
    local_agent_playwright_allowed: bool = False,
    local_system_browser_required: bool = False,
    api_connector_required: bool = False,
    user_present_required: bool = False,
    automation_blocked: bool = False,
    fallback_allowed: bool = False,
    fallback_route: str = "",
    block_reason: str = "",
    message_ko: str = "",
) -> dict[str, Any]:
    automation_blocked = automation_blocked or (recommended_route == ROUTE_BLOCK)
    safe_to_dispatch = recommended_route in (
        ROUTE_SERVER_PLAYWRIGHT_READONLY,
        ROUTE_LOCAL_AGENT_PLAYWRIGHT_READONLY,
    )
    return {
        "engine_capability": engine_capability,
        "recommended_route": recommended_route,
        "server_playwright_allowed": server_playwright_allowed,
        "local_agent_playwright_allowed": local_agent_playwright_allowed,
        "local_system_browser_required": local_system_browser_required,
        "api_connector_required": api_connector_required,
        "user_present_required": user_present_required,
        "automation_blocked": automation_blocked,
        "fallback_allowed": fallback_allowed,
        "fallback_route": fallback_route,
        "block_reason": block_reason,
        "safe_to_dispatch": safe_to_dispatch,
        "safe_to_execute": False,
        "message_ko": message_ko,
    }
