"""External Site Auth Policy Registry.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

모든 외부 사이트의 인증 정책을 단일 소스로 검증한다.
쿠키/토큰/비밀번호 저장 금지. 서버 원격 로그인 금지.
"""
from __future__ import annotations

from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY, get_provider

# ---------------------------------------------------------------------------
# 인증 정책 분류 상수
# ---------------------------------------------------------------------------

POLICY_USER_PRESENT_REQUIRED          = "USER_PRESENT_REQUIRED"
POLICY_DESKTOP_BROWSER_REQUIRED       = "DESKTOP_BROWSER_REQUIRED"
POLICY_OFFICIAL_OAUTH_ALLOWED         = "OFFICIAL_OAUTH_ALLOWED"
POLICY_SERVER_REMOTE_LOGIN_FORBIDDEN  = "SERVER_REMOTE_LOGIN_FORBIDDEN"
POLICY_COOKIE_STORAGE_FORBIDDEN       = "COOKIE_STORAGE_FORBIDDEN"
POLICY_TOKEN_STORAGE_FORBIDDEN        = "TOKEN_STORAGE_FORBIDDEN"
POLICY_BROWSER_PROFILE_REUSE_ALLOWED  = "BROWSER_PROFILE_REUSE_ALLOWED"
POLICY_CERTIFICATE_USER_PRESENT       = "CERTIFICATE_USER_PRESENT_REQUIRED"

# ---------------------------------------------------------------------------
# 정책 검증 함수
# ---------------------------------------------------------------------------

def get_auth_policies(provider_id: str) -> list[str]:
    p = get_provider(provider_id)
    if p is None:
        return []
    policies = []
    if p.user_present_login_required:
        policies.append(POLICY_USER_PRESENT_REQUIRED)
    if p.desktop_app_required:
        policies.append(POLICY_DESKTOP_BROWSER_REQUIRED)
    if p.official_api_preferred:
        policies.append(POLICY_OFFICIAL_OAUTH_ALLOWED)
    if not p.server_remote_login_allowed:
        policies.append(POLICY_SERVER_REMOTE_LOGIN_FORBIDDEN)
    if not p.cookie_storage_allowed:
        policies.append(POLICY_COOKIE_STORAGE_FORBIDDEN)
    if not p.token_storage_allowed:
        policies.append(POLICY_TOKEN_STORAGE_FORBIDDEN)
    if p.browser_profile_reuse_allowed:
        policies.append(POLICY_BROWSER_PROFILE_REUSE_ALLOWED)
    if p.certificate_login_required:
        policies.append(POLICY_CERTIFICATE_USER_PRESENT)
    return policies


def assert_no_server_remote_login() -> list[str]:
    """server_remote_login_allowed=True인 provider가 없는지 확인."""
    violations = []
    for p in PROVIDER_REGISTRY:
        if p.server_remote_login_allowed:
            violations.append(f"{p.provider_id}: server_remote_login_allowed=True 위반")
    return violations


def assert_no_cookie_storage() -> list[str]:
    """cookie_storage_allowed=True인 provider가 없는지 확인."""
    violations = []
    for p in PROVIDER_REGISTRY:
        if p.cookie_storage_allowed:
            violations.append(f"{p.provider_id}: cookie_storage_allowed=True 위반")
    return violations


def assert_critical_has_approval_gate() -> list[str]:
    """CRITICAL 위험도 provider가 모두 approval_gate_required=True인지 확인."""
    from ai_orchestrator.external_sites.provider_models import RISK_CRITICAL
    violations = []
    for p in PROVIDER_REGISTRY:
        if p.risk_level == RISK_CRITICAL and not p.approval_gate_required:
            violations.append(f"{p.provider_id}: CRITICAL인데 approval_gate_required=False 위반")
    return violations


def assert_no_headless_for_critical() -> list[str]:
    """CRITICAL provider가 headless_allowed=True가 아닌지 확인."""
    from ai_orchestrator.external_sites.provider_models import RISK_CRITICAL
    violations = []
    for p in PROVIDER_REGISTRY:
        if p.risk_level == RISK_CRITICAL and p.headless_allowed:
            violations.append(f"{p.provider_id}: CRITICAL인데 headless_allowed=True 위반")
    return violations


__all__ = [
    "get_auth_policies",
    "assert_no_server_remote_login",
    "assert_no_cookie_storage",
    "assert_critical_has_approval_gate",
    "assert_no_headless_for_critical",
    "POLICY_USER_PRESENT_REQUIRED",
    "POLICY_DESKTOP_BROWSER_REQUIRED",
    "POLICY_OFFICIAL_OAUTH_ALLOWED",
    "POLICY_SERVER_REMOTE_LOGIN_FORBIDDEN",
    "POLICY_COOKIE_STORAGE_FORBIDDEN",
    "POLICY_TOKEN_STORAGE_FORBIDDEN",
    "POLICY_BROWSER_PROFILE_REUSE_ALLOWED",
    "POLICY_CERTIFICATE_USER_PRESENT",
]
