"""
콘텐츠 workflow 정책

네이버 카페/블로그 workflow에서 사용하는 action 분류 및 정책.
delegated_permission 모델에 따른 실행 등급 정의.
"""

from __future__ import annotations

from ai_orchestrator.contracts.action_risk_policy import (
    GRADE_AUTO_ALLOWED,
    GRADE_USER_DELEGATED,
    GRADE_USER_DIRECT,
    classify_action,
)

# ── 카페 workflow action 목록 ─────────────────────────────────────────────────

CAFE_READ_ACTIONS: frozenset[str] = frozenset(
    {
        "search",
        "read_page",
        "extract_text",
        "extract_table",
        "extract_list",
        "extract_metadata",
        "capture_screenshot",
        "detect_login_status",
    }
)

CAFE_WRITE_ACTIONS: frozenset[str] = frozenset(
    {
        "cafe_post_write",
        "cafe_comment_write",
        "cafe_post_edit",
        "cafe_comment_edit",
        "cafe_post_delete",
        "cafe_comment_delete",
    }
)

CAFE_DRAFT_ACTIONS: frozenset[str] = frozenset(
    {
        "save_draft",
        "preview",
    }
)

# ── 블로그 workflow action 목록 ───────────────────────────────────────────────

BLOG_READ_ACTIONS: frozenset[str] = frozenset(
    {
        "read_page",
        "extract_text",
        "extract_table",
        "capture_screenshot",
        "detect_login_status",
        "search",
    }
)

BLOG_DRAFT_ACTIONS: frozenset[str] = frozenset(
    {
        "save_draft",
        "preview",
    }
)

BLOG_PUBLISH_ACTIONS: frozenset[str] = frozenset(
    {
        "blog_publish",
        "blog_schedule_publish",
        "blog_edit",
        "blog_delete",
        "blog_set_visibility",
        "set_visibility",
        "publish_with_attachment",
    }
)

# ── workflow 단계별 필요 grade ─────────────────────────────────────────────────

WORKFLOW_GRADE_MAP: dict[str, str] = {
    # 카페 읽기
    "cafe_search": GRADE_AUTO_ALLOWED,
    "cafe_read_list": GRADE_AUTO_ALLOWED,
    "cafe_read_post": GRADE_AUTO_ALLOWED,
    "cafe_extract_summary": GRADE_AUTO_ALLOWED,
    "cafe_extract_keywords": GRADE_AUTO_ALLOWED,
    "cafe_generate_draft": GRADE_AUTO_ALLOWED,
    "cafe_generate_comment_candidate": GRADE_AUTO_ALLOWED,
    # 카페 쓰기
    "cafe_post_write": GRADE_USER_DELEGATED,
    "cafe_comment_write": GRADE_USER_DELEGATED,
    "cafe_post_edit": GRADE_USER_DELEGATED,
    "cafe_post_delete": GRADE_USER_DELEGATED,
    "cafe_comment_edit": GRADE_USER_DELEGATED,
    "cafe_comment_delete": GRADE_USER_DELEGATED,
    # 블로그 초안
    "blog_generate_title": GRADE_AUTO_ALLOWED,
    "blog_generate_body": GRADE_AUTO_ALLOWED,
    "blog_generate_tags": GRADE_AUTO_ALLOWED,
    "blog_preview": GRADE_AUTO_ALLOWED,
    "blog_save_draft": GRADE_AUTO_ALLOWED,
    # 블로그 발행
    "blog_publish": GRADE_USER_DELEGATED,
    "blog_schedule_publish": GRADE_USER_DELEGATED,
    "blog_edit": GRADE_USER_DELEGATED,
    "blog_delete": GRADE_USER_DELEGATED,
    "blog_set_visibility": GRADE_USER_DELEGATED,
    # 로그인 (사용자 직접)
    "naver_login": GRADE_USER_DIRECT,
    "login_password_input": GRADE_USER_DIRECT,
    "otp_input": GRADE_USER_DIRECT,
}


def get_workflow_grade(step: str) -> str:
    """workflow 단계의 실행 등급을 반환한다."""
    if step in WORKFLOW_GRADE_MAP:
        return WORKFLOW_GRADE_MAP[step]
    # delegated_permission action_risk_policy 위임
    return classify_action(step)


def requires_permission(step: str) -> bool:
    return get_workflow_grade(step) == GRADE_USER_DELEGATED


def is_workflow_auto_allowed(step: str) -> bool:
    return get_workflow_grade(step) == GRADE_AUTO_ALLOWED


# ── 네이버 도메인 상수 ────────────────────────────────────────────────────────

NAVER_DOMAINS: frozenset[str] = frozenset(
    {
        "naver.com",
        "www.naver.com",
        "nid.naver.com",
        "cafe.naver.com",
        "m.cafe.naver.com",
        "blog.naver.com",
        "m.blog.naver.com",
    }
)

NAVER_CAFE_DOMAINS: frozenset[str] = frozenset(
    {
        "cafe.naver.com",
        "m.cafe.naver.com",
    }
)

NAVER_BLOG_DOMAINS: frozenset[str] = frozenset(
    {
        "blog.naver.com",
        "m.blog.naver.com",
    }
)

NAVER_LOGIN_DOMAIN = "www.naver.com"
