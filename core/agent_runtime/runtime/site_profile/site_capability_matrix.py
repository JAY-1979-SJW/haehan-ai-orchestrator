"""
Site Capability Matrix

사이트가 어떤 기능을 지원하는지 공통 capability로 표현한다.
capability → 실행 등급 매핑.
"""
from __future__ import annotations

from typing import Any

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_BLOCKED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
)
from core.agent_runtime.runtime.site_profile.site_profile_registry import get_site_profile

# ── Capability 상수 ───────────────────────────────────────────────────────────

CAP_READONLY_EXPLORE       = "READONLY_EXPLORE"
CAP_SEARCH                 = "SEARCH"
CAP_EXTRACT_TEXT           = "EXTRACT_TEXT"
CAP_EXTRACT_TABLE          = "EXTRACT_TABLE"
CAP_DOWNLOAD               = "DOWNLOAD"
CAP_UPLOAD                 = "UPLOAD"
CAP_DRAFT_GENERATE         = "DRAFT_GENERATE"
CAP_FORM_FILL_NON_SENSITIVE= "FORM_FILL_NON_SENSITIVE"
CAP_SAVE_DRAFT             = "SAVE_DRAFT"
CAP_PREVIEW                = "PREVIEW"
CAP_PUBLISH_WITH_PERMISSION= "PUBLISH_WITH_PERMISSION"
CAP_COMMENT_WITH_PERMISSION= "COMMENT_WITH_PERMISSION"
CAP_MESSAGE_WITH_PERMISSION= "MESSAGE_WITH_PERMISSION"
CAP_DELETE_WITH_PERMISSION = "DELETE_WITH_PERMISSION"
CAP_PAYMENT_DIRECT_ONLY    = "PAYMENT_DIRECT_ONLY"
CAP_ESIGN_DIRECT_ONLY      = "ESIGN_DIRECT_ONLY"
CAP_BID_DIRECT_ONLY        = "BID_DIRECT_ONLY"

# ── Capability → 실행 등급 매핑 ───────────────────────────────────────────────

_CAPABILITY_GRADE: dict[str, str] = {
    CAP_READONLY_EXPLORE:        GRADE_AUTO_ALLOWED,
    CAP_SEARCH:                  GRADE_AUTO_ALLOWED,
    CAP_EXTRACT_TEXT:            GRADE_AUTO_ALLOWED,
    CAP_EXTRACT_TABLE:           GRADE_AUTO_ALLOWED,
    CAP_DOWNLOAD:                GRADE_AUTO_ALLOWED,
    CAP_DRAFT_GENERATE:          GRADE_AUTO_ALLOWED,
    CAP_FORM_FILL_NON_SENSITIVE: GRADE_AUTO_ALLOWED,
    CAP_SAVE_DRAFT:              GRADE_AUTO_ALLOWED,
    CAP_PREVIEW:                 GRADE_AUTO_ALLOWED,
    CAP_UPLOAD:                  GRADE_USER_DELEGATED,
    CAP_PUBLISH_WITH_PERMISSION: GRADE_USER_DELEGATED,
    CAP_COMMENT_WITH_PERMISSION: GRADE_USER_DELEGATED,
    CAP_MESSAGE_WITH_PERMISSION: GRADE_USER_DELEGATED,
    CAP_DELETE_WITH_PERMISSION:  GRADE_USER_DELEGATED,
    CAP_PAYMENT_DIRECT_ONLY:     GRADE_USER_DIRECT,
    CAP_ESIGN_DIRECT_ONLY:       GRADE_USER_DIRECT,
    CAP_BID_DIRECT_ONLY:         GRADE_USER_DIRECT,
}

# ── Action → Capability 역매핑 (대표적인 것만) ────────────────────────────────

_ACTION_TO_CAPABILITY: dict[str, str] = {
    "read_page":        CAP_READONLY_EXPLORE,
    "open_url":         CAP_READONLY_EXPLORE,
    "search":           CAP_SEARCH,
    "extract_text":     CAP_EXTRACT_TEXT,
    "extract_table":    CAP_EXTRACT_TABLE,
    "download_file":    CAP_DOWNLOAD,
    "generate_draft":   CAP_DRAFT_GENERATE,
    "save_draft":       CAP_SAVE_DRAFT,
    "preview":          CAP_PREVIEW,
    "blog_publish":     CAP_PUBLISH_WITH_PERMISSION,
    "blog_schedule_publish": CAP_PUBLISH_WITH_PERMISSION,
    "blog_edit":        CAP_PUBLISH_WITH_PERMISSION,
    "blog_delete":      CAP_DELETE_WITH_PERMISSION,
    "cafe_post_write":  CAP_PUBLISH_WITH_PERMISSION,
    "cafe_comment_write": CAP_COMMENT_WITH_PERMISSION,
    "cafe_post_delete": CAP_DELETE_WITH_PERMISSION,
    "forum_post_write": CAP_PUBLISH_WITH_PERMISSION,
    "forum_comment_write": CAP_COMMENT_WITH_PERMISSION,
    "send_message":     CAP_MESSAGE_WITH_PERMISSION,
    "send_email":       CAP_MESSAGE_WITH_PERMISSION,
    "file_upload":      CAP_UPLOAD,
    "payment_final_submit": CAP_PAYMENT_DIRECT_ONLY,
    "confirm_payment":  CAP_PAYMENT_DIRECT_ONLY,
    "e_signature":      CAP_ESIGN_DIRECT_ONLY,
    "e_sign":           CAP_ESIGN_DIRECT_ONLY,
    "bid_final_submit": CAP_BID_DIRECT_ONLY,
}


def capability_allowed(site_id: str, capability: str) -> bool:
    """해당 site가 capability를 지원하는지 확인."""
    profile = get_site_profile(site_id)
    if not profile:
        return False
    return capability in profile.get("supported_capabilities", [])


def get_required_risk_level(site_id: str, capability: str) -> str:
    """capability의 실행 등급 반환. 미등록 capability → USER_DELEGATED (보수적)."""
    return _CAPABILITY_GRADE.get(capability, GRADE_USER_DELEGATED)


def get_capability_for_action(action: str) -> str | None:
    """action에 해당하는 capability 반환."""
    return _ACTION_TO_CAPABILITY.get(action)


def get_required_permission(site_id: str, action: str) -> dict[str, Any]:
    """
    action 실행에 필요한 권한 정보 반환.

    반환:
      capability: str
      grade: str
      requires_permission: bool
      site_id: str
    """
    cap = get_capability_for_action(action)
    grade = _CAPABILITY_GRADE.get(cap, GRADE_USER_DELEGATED) if cap else GRADE_USER_DELEGATED

    from core.agent_runtime.runtime.site_profile.site_profile_registry import (
        is_action_blocked_for_site,
        is_action_direct_required,
    )
    if is_action_blocked_for_site(site_id, action):
        grade = GRADE_BLOCKED
    elif is_action_direct_required(site_id, action):
        grade = GRADE_USER_DIRECT

    return {
        "site_id": site_id,
        "action": action,
        "capability": cap,
        "grade": grade,
        "requires_permission": grade == GRADE_USER_DELEGATED,
    }


def reject_if_blocked(site_id: str, action: str) -> dict[str, Any] | None:
    """
    BLOCKED action이면 차단 dict 반환. 아니면 None.
    """
    from core.agent_runtime.runtime.site_profile.site_profile_registry import is_action_blocked_for_site
    if is_action_blocked_for_site(site_id, action):
        return {
            "blocked": True,
            "site_id": site_id,
            "action": action,
            "reason": f"BLOCKED action: {action!r} on site {site_id!r}",
        }
    return None


def get_all_capabilities() -> list[str]:
    return list(_CAPABILITY_GRADE.keys())
