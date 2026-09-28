"""Browser Worker execution policy."""

import os
from urllib.parse import urlparse

# Allowed actions in dry_run mode only
ALLOWED_ACTIONS_DRY_RUN = frozenset(
    {
        "browser.inspect",
    }
)

# Allowed actions in actual execution mode (gated by BROWSER_EXECUTION_ENABLED)
ALLOWED_ACTIONS_ACTUAL_EXECUTION = frozenset(
    {
        "browser.inspect",
        "browser.open_url_controlled",
        "browser.open_click_close_controlled",
    }
)

# Allowed URLs in actual execution mode
ALLOWED_URLS_ACTUAL_EXECUTION = frozenset(
    {
        "about:blank",
        "https://example.com/",
    }
)

# Actions disabled in actual execution mode
DISABLED_ACTIONS_ACTUAL = frozenset(
    {
        "browser.inspect",
        "browser.plan_click",
        "browser.plan_type",
        "browser.plan_submit",
        "browser.execute_click",
        "browser.execute_type",
    }
)


# ── 서버 브라우저 URL 경계 정책 ───────────────────────────────────────────────
# ai_orchestrator/browser_tool/server_browser_boundary_policy.py와 동일한
# decision 문자열을 사용한다. 순환 import 방지를 위해 독립 상수로 정의.

DECISION_SERVER_BROWSER_ALLOWED_READONLY = "SERVER_BROWSER_ALLOWED_READONLY"
DECISION_REQUIRE_LOCAL_AGENT = "REQUIRE_LOCAL_AGENT"
DECISION_REQUIRE_API_CONNECTOR = "REQUIRE_API_CONNECTOR"
DECISION_REQUIRE_USER_PRESENT = "REQUIRE_USER_PRESENT"
DECISION_BLOCK = "BLOCK"

# 서버 브라우저에서 허용되는 URL (완전 일치 또는 안전 prefix)
_ALLOWED_SERVER_BROWSER_URLS: frozenset[str] = frozenset(
    {
        "about:blank",
        "https://example.com/",
        "https://example.com",
    }
)

# 허용 URL prefix (data: 테스트 페이지)
_ALLOWED_URL_PREFIXES: tuple[str, ...] = ("data:text/html",)

# 서버 브라우저 금지 도메인 키워드
_FORBIDDEN_DOMAIN_KEYWORDS: tuple[str, ...] = (
    # 은행
    "kbstar",
    "shinhan",
    "wooribank",
    "hanabank",
    "ibk",
    "nonghy",
    "kakaobank",
    "tossbank",
    "sc.com",
    "citi",
    "bnk",
    "dgb",
    "kjb",
    "jb.co.kr",
    # 카드
    "card.kb",
    "shinhancard",
    "hyundaicard",
    "samsungcard",
    "lottec",
    "bccard",
    "hanacard",
    "wooricard",
    "citicard",
    # 세무
    "hometax.go.kr",
    "sontax",
    "etax.seoul",
    # 정부/민원
    "gov.kr",
    "mois.go.kr",
    "minwon",
    "egov",
    "g4c",
    # 4대보험
    "4insure",
    "nhis.or.kr",
    "nps.or.kr",
    "kcomwel",
    "ei.go.kr",
    # 인증서 포털
    "yessign",
    "signgate",
    "crosscert",
    "tradesign",
    "npki",
    # Google 계정 로그인
    "accounts.google.com",
    # 이메일/드라이브 (API 전용)
    "mail.google.com",
    "drive.google.com",
    "calendar.google.com",
    "docs.google.com",
    "sheets.google.com",
)

# 서버 브라우저 금지 메타데이터 플래그
_FORBIDDEN_METADATA_FLAGS: tuple[str, ...] = (
    "requires_certificate",
    "requires_financial_certificate",
    "requires_otp",
    "requires_password",
    "requires_captcha",
    "requires_security_plugin",
    "user_present_required",
    "local_agent_required",
)


def evaluate_server_browser_url_policy(
    url: str,
    metadata: dict | None = None,
) -> dict:
    """
    서버 브라우저에서 URL을 열기 전 경계 정책을 판정한다.

    반환:
    - allowed (bool)
    - decision (str)
    - block_reason (str)
    - execution_location_required (str)
    - safe_to_execute (False 고정)
    - message_ko (str)
    """
    meta = metadata or {}
    url_clean = (url or "").strip()

    # 1. production_mode 강제 차단
    if meta.get("production_mode") is True:
        return _block("PRODUCTION_MODE_SERVER_BROWSER_BLOCKED", "production_mode=true: 서버 브라우저 실행 차단.")

    # 2. 메타데이터 플래그 기반 차단 (page.goto 이전 단계)
    for flag in _FORBIDDEN_METADATA_FLAGS:
        if meta.get(flag) is True:
            if flag == "requires_captcha":
                return _block(DECISION_BLOCK, f"{flag}: CAPTCHA 요구 사이트. 서버 브라우저 금지.")
            if flag in (
                "requires_certificate",
                "requires_financial_certificate",
                "requires_otp",
                "requires_password",
                "user_present_required",
            ):
                return _block(DECISION_REQUIRE_USER_PRESENT, f"{flag}: 사용자 직접 인증 필요. 서버 브라우저 금지.")
            return _block(DECISION_REQUIRE_LOCAL_AGENT, f"{flag}: 로컬 Agent 필요. 서버 브라우저 금지.")

    # 3. 빈 URL은 about:blank로 간주 허용
    if not url_clean or url_clean == "about:blank":
        return _allow()

    # 4. data: 테스트 prefix 허용
    for prefix in _ALLOWED_URL_PREFIXES:
        if url_clean.startswith(prefix):
            return _allow()

    # 5. 완전 일치 허용 URL
    if url_clean in _ALLOWED_SERVER_BROWSER_URLS:
        return _allow()

    # 6. 금지 도메인 키워드 검사
    try:
        parsed = urlparse(url_clean)
        host = (parsed.netloc or "").lower()
    except Exception:  # noqa: BLE001 - URL host 파싱 실패 시 URL 원문 전체를 host로 간주해 금지 도메인 키워드 검사(substring 매칭)를 계속 진행 - 파싱 실패가 오히려 더 넓게 매칭되어 차단 방향으로 작동하며, 뒤이은 '미분류 외부 도메인 기본 차단' 로직으로 인해 결과적으로 fail-closed(알 수 없으면 차단)
        host = url_clean.lower()

    for kw in _FORBIDDEN_DOMAIN_KEYWORDS:
        if kw in host:
            if "accounts.google.com" in host:
                return _block(DECISION_BLOCK, "Google 계정 로그인 페이지. 서버 브라우저 금지.")
            if any(
                g in host for g in ("mail.google", "drive.google", "calendar.google", "docs.google", "sheets.google")
            ):
                return _block(DECISION_REQUIRE_API_CONNECTOR, "Google 서비스. 공식 API/OAuth만 허용.")
            return _block(DECISION_REQUIRE_LOCAL_AGENT, f"제한 도메인({kw}). 서버 브라우저 금지.")

    # 7. 알 수 없는 외부 도메인 → 기본 차단
    if host and host not in ("example.com", "www.example.com"):
        return _block(DECISION_REQUIRE_LOCAL_AGENT, f"미분류 외부 도메인({host}). 서버 브라우저 기본 차단.")

    return _allow()


def _allow() -> dict:
    return {
        "allowed": True,
        "decision": DECISION_SERVER_BROWSER_ALLOWED_READONLY,
        "block_reason": "",
        "execution_location_required": "SERVER_BROWSER",
        "safe_to_execute": False,
        "message_ko": "서버 브라우저 접근 허용 (read-only).",
    }


def _block(decision: str, reason: str) -> dict:
    loc = {
        DECISION_REQUIRE_LOCAL_AGENT: "LOCAL_AGENT",
        DECISION_REQUIRE_API_CONNECTOR: "API_ONLY",
        DECISION_REQUIRE_USER_PRESENT: "USER_PRESENT_ONLY",
        DECISION_BLOCK: "BLOCKED",
    }.get(decision, "BLOCKED")
    return {
        "allowed": False,
        "decision": decision,
        "block_reason": reason,
        "execution_location_required": loc,
        "safe_to_execute": False,
        "message_ko": reason,
    }


def is_action_allowed_dry_run(action: str) -> bool:
    """Check if action is allowed in dry_run mode."""
    return action in ALLOWED_ACTIONS_DRY_RUN


def is_action_known(action: str) -> bool:
    """Check if action is known (defined)."""
    return action in DISABLED_ACTIONS_ACTUAL or action in ALLOWED_ACTIONS_DRY_RUN


# Security policies
class WorkerSecurityPolicy:
    """Browser Worker security and operational policies."""

    @staticmethod
    def validate_dry_run(action: str) -> tuple[bool, str]:
        """Validate dry_run request.

        Returns:
            (allowed, reason)
        """
        if not is_action_allowed_dry_run(action):
            return False, f"Action '{action}' not allowed in dry_run mode"
        return True, "ok"

    @staticmethod
    def validate_actual_execution(action: str, url: str = "") -> tuple[bool, str]:
        """Validate actual execution request with precise error codes.

        Returns:
            (allowed, error_code or "ok")

        Error code precedence (checked in order):
            1. ACTION_NOT_ALLOWED_ACTUAL_EXECUTION
            2. URL_NOT_ALLOWED_ACTUAL_EXECUTION
            3. ACTUAL_BROWSER_EXECUTION_NOT_ENABLED
        """
        # Check 1: action allowlist (highest priority)
        if action not in ALLOWED_ACTIONS_ACTUAL_EXECUTION:
            return False, "ACTION_NOT_ALLOWED_ACTUAL_EXECUTION"

        # Check 2: URL allowlist (second priority)
        if url and url not in ALLOWED_URLS_ACTUAL_EXECUTION:
            return False, "URL_NOT_ALLOWED_ACTUAL_EXECUTION"

        # Check 3: env flag (lowest priority)
        if os.environ.get("BROWSER_EXECUTION_ENABLED", "").lower() != "true":
            return False, "ACTUAL_BROWSER_EXECUTION_NOT_ENABLED"

        return True, "ok"

    @staticmethod
    def get_security_notes() -> list[str]:
        """Get security and operational notes."""
        return [
            "Task-specific browser context (no context sharing)",
            "Cookies/sessions stored in memory only (no persistence)",
            "Screenshots and temp files deleted after task completion",
            "Login/authentication tasks routed to local_agent_backend",
            "Chromium browser only (Firefox/WebKit not supported)",
        ]
