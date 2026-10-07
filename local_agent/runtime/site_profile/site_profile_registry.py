"""
Site Profile Registry

사이트별 자동화 정책을 코드가 아닌 profile로 관리한다.
새 사이트 추가 시 코드 수정 없이 profile만 등록한다.
"""
from __future__ import annotations

from typing import Any

# ── 로그인 정책 상수 ──────────────────────────────────────────────────────────

LOGIN_USER_DIRECT = "USER_DIRECT_REQUIRED"
LOGIN_WAITING_AUTH = "WAITING_USER_AUTH"
LOGIN_NOT_REQUIRED = "NOT_REQUIRED"

# ── 카테고리 상수 ─────────────────────────────────────────────────────────────

CAT_CONTENT_PLATFORM = "content_platform"
CAT_GOVERNMENT = "government"
CAT_FINANCIAL = "financial"
CAT_ECOMMERCE = "ecommerce"
CAT_FORUM = "forum"
CAT_PORTAL = "portal"
CAT_GENERIC = "generic"

# ── 공통 차단 action ─────────────────────────────────────────────────────────

_COMMON_BLOCKED = [
    "password_save", "otp_save", "certificate_password_save",
    "cookie_export", "session_export", "token_export",
    "storage_state_export", "cert_file_access", "npki_access",
    "captcha_bypass", "account_bypass", "stealth_evasion",
    "bulk_spam_post", "bulk_spam_comment",
    "unauthorized_publish", "unauthorized_delete",
    "auto_payment", "auto_transfer", "auto_bid_submit", "auto_esign",
]

_COMMON_DIRECT = [
    "login_password_input", "otp_input", "certificate_password_input",
    "e_signature", "identity_verification_confirm",
]

_COMMON_FINANCIAL_DIRECT = _COMMON_DIRECT + [
    "payment_final_submit", "money_transfer", "contract_final_submit",
]

_COMMON_GOVERNMENT_DIRECT = _COMMON_DIRECT + [
    "bid_final_submit", "government_final_submit", "legal_final_submit",
    "certificate_selection",
]


def _profile(  # noqa: PLR0913 - 공개 시그니처 유지(키워드 인자 호환)
    site_id: str,
    display_name: str,
    domains: list[str],
    category: str,
    default_execution: str = "LOCAL_BROWSER_DEFAULT",
    login_policy: str = LOGIN_USER_DIRECT,
    supported_capabilities: list[str] | None = None,
    delegated_actions: list[str] | None = None,
    direct_required_actions: list[str] | None = None,
    blocked_actions: list[str] | None = None,
    max_default_executions: int = 1,
    requires_audit_log: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "display_name": display_name,
        "domains": domains,
        "category": category,
        "default_execution": default_execution,
        "login_policy": login_policy,
        "supported_capabilities": supported_capabilities or [],
        "delegated_actions": delegated_actions or [],
        "direct_required_actions": direct_required_actions or _COMMON_DIRECT,
        "blocked_actions": blocked_actions or list(_COMMON_BLOCKED),
        "max_default_executions": max_default_executions,
        "requires_audit_log": requires_audit_log,
        "notes": notes,
    }


# ── 등록된 Site Profile ────────────────────────────────────────────────────────

_REGISTRY: dict[str, dict[str, Any]] = {

    "naver": _profile(
        site_id="naver",
        display_name="네이버",
        domains=["naver.com", "www.naver.com"],
        category=CAT_PORTAL,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD", "DRAFT_GENERATE",
        ],
        delegated_actions=[],
        direct_required_actions=_COMMON_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="네이버 포털. 탐색/검색 AUTO_ALLOWED.",
    ),

    "naver_blog": _profile(
        site_id="naver_blog",
        display_name="네이버 블로그",
        domains=["blog.naver.com", "m.blog.naver.com"],
        category=CAT_CONTENT_PLATFORM,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD", "DRAFT_GENERATE", "SAVE_DRAFT", "PREVIEW",
            "PUBLISH_WITH_PERMISSION", "DELETE_WITH_PERMISSION",
        ],
        delegated_actions=[
            "blog_publish", "blog_schedule_publish",
            "blog_edit", "blog_delete", "blog_set_visibility",
            "upload_attachment_to_post", "change_visibility",
        ],
        direct_required_actions=_COMMON_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="네이버 블로그. 발행/수정/삭제 USER_DELEGATED.",
    ),

    "naver_cafe": _profile(
        site_id="naver_cafe",
        display_name="네이버 카페",
        domains=["cafe.naver.com", "m.cafe.naver.com"],
        category=CAT_FORUM,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD", "DRAFT_GENERATE",
            "PUBLISH_WITH_PERMISSION", "COMMENT_WITH_PERMISSION",
            "DELETE_WITH_PERMISSION",
        ],
        delegated_actions=[
            "cafe_post_write", "cafe_post_edit", "cafe_post_delete",
            "cafe_comment_write", "cafe_comment_edit", "cafe_comment_delete",
            "upload_attachment_to_post",
        ],
        direct_required_actions=_COMMON_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="네이버 카페. 탐색 AUTO_ALLOWED. 글쓰기/댓글 USER_DELEGATED.",
    ),

    "g2b_public": _profile(
        site_id="g2b_public",
        display_name="나라장터 공개",
        domains=["www.g2b.go.kr", "g2b.go.kr"],
        category=CAT_GOVERNMENT,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD",
        ],
        delegated_actions=[],
        direct_required_actions=_COMMON_GOVERNMENT_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED) + [
            "bid_submit", "e_signature", "contract_submit",
        ],
        notes="나라장터 공개 공고 read-only. 투찰/서명은 USER_DIRECT.",
    ),

    "hometax_placeholder": _profile(
        site_id="hometax_placeholder",
        display_name="홈택스 (placeholder)",
        domains=["www.hometax.go.kr", "hometax.go.kr"],
        category=CAT_GOVERNMENT,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=[
            "READONLY_EXPLORE", "EXTRACT_TEXT", "DOWNLOAD",
        ],
        delegated_actions=[],
        direct_required_actions=_COMMON_GOVERNMENT_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED) + ["tax_submit"],
        notes="홈택스 placeholder. 실제 로그인/신고는 USER_DIRECT. 조회만 허용.",
    ),

    "bank_placeholder": _profile(
        site_id="bank_placeholder",
        display_name="은행 (placeholder)",
        domains=[],
        category=CAT_FINANCIAL,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=["READONLY_EXPLORE", "EXTRACT_TEXT", "DOWNLOAD"],
        delegated_actions=[],
        direct_required_actions=_COMMON_FINANCIAL_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="은행 placeholder. 실제 이체/결제는 USER_DIRECT. 조회만 허용.",
    ),

    "card_placeholder": _profile(
        site_id="card_placeholder",
        display_name="카드사 (placeholder)",
        domains=[],
        category=CAT_FINANCIAL,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=["READONLY_EXPLORE", "EXTRACT_TEXT", "DOWNLOAD"],
        delegated_actions=[],
        direct_required_actions=_COMMON_FINANCIAL_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="카드사 placeholder. 결제는 USER_DIRECT. 내역 조회만 허용.",
    ),

    "insurance_placeholder": _profile(
        site_id="insurance_placeholder",
        display_name="보험사 (placeholder)",
        domains=[],
        category=CAT_FINANCIAL,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=["READONLY_EXPLORE", "EXTRACT_TEXT", "DOWNLOAD"],
        delegated_actions=[],
        direct_required_actions=_COMMON_FINANCIAL_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="보험사 placeholder. 보험금 청구는 USER_DIRECT. 조회만 허용.",
    ),

    "generic_content_site": _profile(
        site_id="generic_content_site",
        display_name="일반 콘텐츠 사이트",
        domains=[],
        category=CAT_CONTENT_PLATFORM,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD", "DRAFT_GENERATE", "SAVE_DRAFT", "PREVIEW",
            "PUBLISH_WITH_PERMISSION", "COMMENT_WITH_PERMISSION",
        ],
        delegated_actions=[
            "blog_publish", "forum_post_write", "forum_comment_write",
            "send_message", "upload_attachment_to_post", "change_visibility",
        ],
        direct_required_actions=_COMMON_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="일반 콘텐츠/블로그/포럼 사이트 기본값.",
    ),

    "generic_government_site": _profile(
        site_id="generic_government_site",
        display_name="일반 정부 사이트",
        domains=[],
        category=CAT_GOVERNMENT,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "DOWNLOAD",
        ],
        delegated_actions=["submit_non_legal_form", "reservation_request"],
        direct_required_actions=_COMMON_GOVERNMENT_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="일반 정부 사이트. 법적 효력 제출은 USER_DIRECT.",
    ),

    "generic_financial_site": _profile(
        site_id="generic_financial_site",
        display_name="일반 금융 사이트",
        domains=[],
        category=CAT_FINANCIAL,
        login_policy=LOGIN_USER_DIRECT,
        supported_capabilities=["READONLY_EXPLORE", "EXTRACT_TEXT", "DOWNLOAD"],
        delegated_actions=[],
        direct_required_actions=_COMMON_FINANCIAL_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="일반 금융 사이트. 결제/이체는 USER_DIRECT.",
    ),

    "generic_forum_site": _profile(
        site_id="generic_forum_site",
        display_name="일반 포럼/커뮤니티",
        domains=[],
        category=CAT_FORUM,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT",
            "PUBLISH_WITH_PERMISSION", "COMMENT_WITH_PERMISSION",
        ],
        delegated_actions=[
            "forum_post_write", "forum_comment_write",
            "send_message", "change_visibility",
        ],
        direct_required_actions=_COMMON_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="일반 포럼/커뮤니티 기본값.",
    ),

    "generic_ecommerce_site": _profile(
        site_id="generic_ecommerce_site",
        display_name="일반 전자상거래",
        domains=[],
        category=CAT_ECOMMERCE,
        login_policy=LOGIN_WAITING_AUTH,
        supported_capabilities=[
            "READONLY_EXPLORE", "SEARCH", "EXTRACT_TEXT", "EXTRACT_TABLE",
            "DOWNLOAD",
        ],
        delegated_actions=["reservation_request", "cancel_reservation_request"],
        direct_required_actions=_COMMON_FINANCIAL_DIRECT,
        blocked_actions=list(_COMMON_BLOCKED),
        notes="일반 전자상거래. 결제는 USER_DIRECT. 조회/예약요청은 DELEGATED.",
    ),
}


def get_site_profile(site_id: str) -> dict[str, Any] | None:
    return dict(_REGISTRY[site_id]) if site_id in _REGISTRY else None


def get_profile_by_domain(domain: str) -> dict[str, Any] | None:
    """도메인으로 site profile 검색. 없으면 None."""
    domain = (domain or "").strip().lower()
    for profile in _REGISTRY.values():
        if domain in profile.get("domains", []):
            return dict(profile)
    return None


def is_site_registered(site_id: str) -> bool:
    return site_id in _REGISTRY


def get_all_site_ids() -> list[str]:
    return list(_REGISTRY.keys())


def is_action_delegated(site_id: str, action: str) -> bool:
    profile = get_site_profile(site_id)
    return bool(profile and action in profile.get("delegated_actions", []))


def is_action_blocked_for_site(site_id: str, action: str) -> bool:
    profile = get_site_profile(site_id)
    return bool(profile and action in profile.get("blocked_actions", []))


def is_action_direct_required(site_id: str, action: str) -> bool:
    profile = get_site_profile(site_id)
    return bool(profile and action in profile.get("direct_required_actions", []))


def register_site_profile(profile: dict[str, Any]) -> None:
    """
    site profile을 레지스트리에 추가한다.
    필수 필드 검증 포함.
    """
    site_id = (profile.get("site_id") or "").strip()
    if not site_id:
        raise ValueError("site_id 필수")
    required = {"site_id", "display_name", "domains", "category"}
    missing = required - set(profile.keys())
    if missing:
        raise ValueError(f"필수 필드 누락: {missing}")
    # blocked_actions 강제 포함
    blocked = set(profile.get("blocked_actions", []))
    blocked.update(_COMMON_BLOCKED)
    profile = dict(profile)
    profile["blocked_actions"] = list(blocked)
    # direct_required_actions 기본값
    if "direct_required_actions" not in profile:
        profile["direct_required_actions"] = list(_COMMON_DIRECT)
    if "requires_audit_log" not in profile:
        profile["requires_audit_log"] = True
    if "max_default_executions" not in profile:
        profile["max_default_executions"] = 1
    _REGISTRY[site_id] = profile
