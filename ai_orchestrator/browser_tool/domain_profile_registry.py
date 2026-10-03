"""
도메인 프로필 레지스트리

사이트별 전용 도구를 만들지 않는다.
사이트별 특성은 profile로만 관리한다.

원칙:
- wildcard 허용 없음
- 실제 확인된 도메인만 등록
- profile은 실행 정책이지 로그인 자동화 코드가 아님
- 미등록 도메인은 conservative 기본값 적용
"""
from __future__ import annotations

from typing import Any

# ── profile 구조 ──────────────────────────────────────────────────────────────

def _profile(  # noqa: PLR0913 - 도메인 프로필 선언 헬퍼, 필드 나열형
    domain: str,
    category: str,
    default_execution: str = "SERVER_FIRST",
    login_execution: str = "LOCAL_REQUIRED",
    security_auth_required: bool = False,
    server_to_local_fallback: bool = True,
    blocked_actions: list[str] | None = None,
    user_direct_actions: list[str] | None = None,
    allowed_readonly: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "domain": domain,
        "category": category,
        "default_execution": default_execution,
        "login_execution": login_execution,
        "security_auth_required": security_auth_required,
        "server_to_local_fallback": server_to_local_fallback,
        "blocked_actions": blocked_actions or [],
        "user_direct_actions": user_direct_actions or [],
        "allowed_readonly": allowed_readonly,
        "notes": notes,
    }


# ── 차단 action 공통 목록 ─────────────────────────────────────────────────────

_COMMON_BLOCKED = [
    "bid_submit", "e_signature", "contract_submit", "payment",
    "cookie_export", "session_export", "password_save", "cert_file_access",
    "auto_sign", "auto_payment", "auto_transfer",
]

_COMMON_USER_DIRECT = [
    "cert_password_input", "otp_input", "final_submit", "confirm_payment",
]

# ── 등록된 domain profile ─────────────────────────────────────────────────────

_REGISTRY: dict[str, dict[str, Any]] = {
    "g2b.go.kr": _profile(
        domain="g2b.go.kr",
        category="government_procurement",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=True,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED,
        user_direct_actions=_COMMON_USER_DIRECT,
        allowed_readonly=True,
        notes="나라장터. 공개 공고 조회는 서버 우선. 로그인/입찰/계약은 로컬 또는 사용자 직접.",
    ),
    "www.g2b.go.kr": _profile(
        domain="www.g2b.go.kr",
        category="government_procurement",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=True,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED,
        user_direct_actions=_COMMON_USER_DIRECT,
        allowed_readonly=True,
        notes="나라장터 www. g2b.go.kr과 동일 정책.",
    ),
    # ── 네이버 ─────────────────────────────────────────────────────────────────
    "naver.com": _profile(
        domain="naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + [
            "bulk_spam_post", "bulk_spam_comment",
            "auto_like", "auto_scrap", "auto_follow",
        ],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 포털. 탐색/읽기 AUTO_ALLOWED. 발행/댓글은 USER_DELEGATED.",
    ),
    "www.naver.com": _profile(
        domain="www.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + [
            "bulk_spam_post", "bulk_spam_comment",
        ],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 www. naver.com과 동일.",
    ),
    "nid.naver.com": _profile(
        domain="nid.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED,
        user_direct_actions=_COMMON_USER_DIRECT + [
            "login_password_input", "otp_input",
        ],
        allowed_readonly=True,
        notes="네이버 로그인. 비밀번호/OTP 자동 입력 금지. WAITING_USER_AUTH 처리.",
    ),
    "cafe.naver.com": _profile(
        domain="cafe.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + [
            "bulk_spam_post", "bulk_spam_comment",
            "auto_like", "auto_scrap",
        ],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 카페. 탐색/읽기 AUTO_ALLOWED. 글쓰기/댓글 USER_DELEGATED.",
    ),
    "m.cafe.naver.com": _profile(
        domain="m.cafe.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + ["bulk_spam_post", "bulk_spam_comment"],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 카페 모바일. cafe.naver.com과 동일.",
    ),
    "blog.naver.com": _profile(
        domain="blog.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + ["bulk_spam_post"],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 블로그. 탐색/읽기 AUTO_ALLOWED. 발행 USER_DELEGATED.",
    ),
    "m.blog.naver.com": _profile(
        domain="m.blog.naver.com",
        category="portal_sns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=False,
        server_to_local_fallback=True,
        blocked_actions=_COMMON_BLOCKED + ["bulk_spam_post"],
        user_direct_actions=_COMMON_USER_DIRECT + ["login_password_input"],
        allowed_readonly=True,
        notes="네이버 블로그 모바일. blog.naver.com과 동일.",
    ),
    # ── 홈택스 ─────────────────────────────────────────────────────────────────
    "hometax.go.kr": _profile(
        domain="hometax.go.kr",
        category="government_tax",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=True,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED + ["tax_submit", "refund_request"],
        user_direct_actions=_COMMON_USER_DIRECT + ["tax_confirm"],
        allowed_readonly=True,
        notes="홈택스. 로그인은 항상 로컬. 서버 fallback 불가 (보안프로그램 필요).",
    ),
    "www.hometax.go.kr": _profile(
        domain="www.hometax.go.kr",
        category="government_tax",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_BROWSER_DEFAULT",
        security_auth_required=True,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED + ["tax_submit", "refund_request"],
        user_direct_actions=_COMMON_USER_DIRECT + ["tax_confirm"],
        allowed_readonly=True,
        notes="홈택스 www. placeholder.",
    ),
    # ── Gabia DNS 관리 ─────────────────────────────────────────────────────────
    "gabia.com": _profile(
        domain="gabia.com",
        category="domain_dns",
        default_execution="LOCAL_BROWSER_DEFAULT",
        login_execution="LOCAL_REQUIRED",
        security_auth_required=False,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED + [
            "dns_final_save", "dns_apply_button_click",
            "domain_transfer", "nameserver_change_submit",
        ],
        user_direct_actions=_COMMON_USER_DIRECT + [
            "dns_save", "dns_apply", "domain_modify_confirm",
        ],
        allowed_readonly=True,
        notes=(
            "가비아 DNS 관리. AI는 DNS 관리 화면까지 진입 및 레코드 입력 준비 가능. "
            "최초 로그인 USER_PRESENT_AUTH 필수. "
            "신뢰 세션 TRUSTED_SESSION_REUSE 허용. "
            "DNS 저장/적용 버튼은 user_direct_actions — 사용자 직접 승인 필수."
        ),
    ),
}

# ── 카테고리별 기본 profile ───────────────────────────────────────────────────

_CATEGORY_DEFAULTS: dict[str, dict[str, Any]] = {
    "bank": _profile(
        domain="*bank*",
        category="financial_banking",
        default_execution="LOCAL_REQUIRED",
        login_execution="LOCAL_REQUIRED",
        security_auth_required=True,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED + ["transfer", "remittance"],
        user_direct_actions=_COMMON_USER_DIRECT + ["confirm_transfer", "otp_confirm"],
        allowed_readonly=False,
        notes="은행 카테고리 기본값. 실제 도메인 등록 필요.",
    ),
    "card": _profile(
        domain="*card*",
        category="financial_card",
        default_execution="LOCAL_REQUIRED",
        login_execution="LOCAL_REQUIRED",
        security_auth_required=True,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED + ["card_payment"],
        user_direct_actions=_COMMON_USER_DIRECT,
        allowed_readonly=False,
        notes="카드사 카테고리 기본값.",
    ),
    "insurance": _profile(
        domain="*insurance*",
        category="financial_insurance",
        default_execution="LOCAL_REQUIRED",
        login_execution="LOCAL_REQUIRED",
        security_auth_required=True,
        server_to_local_fallback=False,
        blocked_actions=_COMMON_BLOCKED,
        user_direct_actions=_COMMON_USER_DIRECT,
        allowed_readonly=False,
        notes="보험사 카테고리 기본값.",
    ),
}

# ── 미등록 도메인 기본값 ──────────────────────────────────────────────────────

_DEFAULT_PROFILE: dict[str, Any] = _profile(
    domain="unknown",
    category="unknown",
    default_execution="LOCAL_BROWSER_DEFAULT",
    login_execution="LOCAL_BROWSER_DEFAULT",
    security_auth_required=False,
    server_to_local_fallback=True,
    blocked_actions=_COMMON_BLOCKED,
    user_direct_actions=_COMMON_USER_DIRECT,
    allowed_readonly=True,
    notes="미등록 도메인 보수적 기본값.",
)


def get_domain_profile(domain: str) -> dict[str, Any]:
    """도메인에 해당하는 profile을 반환한다. 미등록이면 기본값 반환."""
    if not domain:
        return dict(_DEFAULT_PROFILE)
    domain = domain.strip().lower()
    if domain in _REGISTRY:
        return dict(_REGISTRY[domain])
    return dict(_DEFAULT_PROFILE)


def is_domain_registered(domain: str) -> bool:
    """도메인이 레지스트리에 등록되어 있는지 확인한다."""
    return (domain or "").strip().lower() in _REGISTRY


def get_all_registered_domains() -> list[str]:
    """등록된 도메인 목록을 반환한다."""
    return list(_REGISTRY.keys())


def is_action_blocked_for_domain(domain: str, action: str) -> bool:
    """해당 도메인에서 action이 차단되어 있는지 확인한다."""
    profile = get_domain_profile(domain)
    return action in profile.get("blocked_actions", [])


def is_user_direct_action_for_domain(domain: str, action: str) -> bool:
    """해당 도메인에서 action이 사용자 직접 수행 항목인지 확인한다."""
    profile = get_domain_profile(domain)
    return action in profile.get("user_direct_actions", [])


def get_login_execution(domain: str) -> str:
    """해당 도메인의 로그인 실행 위치를 반환한다."""
    return get_domain_profile(domain).get("login_execution", "LOCAL_REQUIRED")


def register_domain_profile(profile: dict[str, Any]) -> None:
    """
    도메인 프로필을 레지스트리에 추가한다.
    wildcard 도메인은 등록 불가.
    """
    domain = (profile.get("domain") or "").strip().lower()
    if not domain or "*" in domain or "?" in domain:
        raise ValueError(f"wildcard 도메인 등록 불가: {domain!r}")
    _REGISTRY[domain] = dict(profile)
