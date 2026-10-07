"""
Selector Pack Registry

사이트별 DOM 차이를 selector pack으로 분리.
자동 로그인/비밀번호/OTP 입력에 사용하지 않는다.
password/OTP/cert_password selector는 저장하지 않는다.
"""

from __future__ import annotations

from typing import Any

# ── 금지 selector 키 ──────────────────────────────────────────────────────────

_FORBIDDEN_SELECTOR_KEYS: frozenset[str] = frozenset(
    {
        "password_input",
        "otp_input",
        "cert_password_input",
        "login_id_input",  # ID는 허용, 비밀번호는 금지
        "login_form_fill",  # 자동 로그인 폼 전체 금지
        "captcha_input",
        "credit_card_input",
        "npki_selector",
    }
)

# ── Selector Pack 예시 ────────────────────────────────────────────────────────

_PACKS: dict[str, dict[str, Any]] = {
    "naver_blog": {
        "site_id": "naver_blog",
        "selectors": {
            "login_required_markers": ["로그인", "아이디", "비밀번호"],
            "publish_button_candidates": ["button:has-text('발행')"],
            "schedule_publish_candidates": ["button:has-text('예약발행')"],
            "save_draft_candidates": ["button:has-text('임시저장')"],
            "title_input_candidates": ["input[title*='제목']", "#title"],
            "body_editor_candidates": ["div[contenteditable='true']", "#postWriteContents"],
            "tag_input_candidates": ["input[placeholder*='태그']"],
            "post_list_candidates": ["ul.post-list li", ".blog_feed_wrap .feed_item"],
            "auth_signal_markers": ["로그인이 필요합니다", "로그인 후 이용"],
        },
    },
    "naver_cafe": {
        "site_id": "naver_cafe",
        "selectors": {
            "login_required_markers": ["로그인", "로그인 후 이용"],
            "write_button_candidates": ["button:has-text('글쓰기')", "a:has-text('글쓰기')"],
            "comment_input_candidates": ["textarea.comment", "#commentContent"],
            "post_submit_candidates": ["button:has-text('등록')", "button:has-text('완료')"],
            "post_list_candidates": [".article-board tbody tr", ".cafe-post-list li"],
            "post_title_candidates": ["h3.title", ".tit-inn"],
            "auth_signal_markers": ["로그인이 필요합니다", "카페 가입이 필요합니다"],
        },
    },
    "g2b_public": {
        "site_id": "g2b_public",
        "selectors": {
            "login_required_markers": ["로그인", "인증서"],
            "notice_list_candidates": ["table.list_info tbody tr", ".bidlist tbody tr"],
            "notice_title_candidates": ["a.tit", "td.title a"],
            "detail_content_candidates": [".view_cont", "#bidPbancDetail"],
            "download_link_candidates": ["a[href*='.pdf']", "a[href*='.hwp']"],
            "auth_signal_markers": ["로그인이 필요합니다", "공동인증서"],
        },
    },
    "generic_content_site": {
        "site_id": "generic_content_site",
        "selectors": {
            "login_required_markers": ["로그인", "login", "sign in"],
            "publish_button_candidates": ["button:has-text('발행')", "button[type='submit']"],
            "save_draft_candidates": ["button:has-text('임시저장')", "button:has-text('draft')"],
            "title_input_candidates": ["input[name='title']", "#title"],
            "body_editor_candidates": ["div[contenteditable='true']", "textarea#content"],
            "auth_signal_markers": ["로그인이 필요합니다", "unauthorized"],
        },
    },
}


def get_selector_pack(site_id: str) -> dict[str, Any] | None:
    return dict(_PACKS[site_id]) if site_id in _PACKS else None


def get_selectors(site_id: str) -> dict[str, list[str]]:
    pack = get_selector_pack(site_id)
    return pack.get("selectors", {}) if pack else {}


def is_pack_registered(site_id: str) -> bool:
    return site_id in _PACKS


def register_selector_pack(site_id: str, selectors: dict[str, list[str]]) -> None:
    """
    selector pack 등록.
    password/OTP/cert_password selector 키 포함 시 오류.
    """
    forbidden_found = set(selectors.keys()) & _FORBIDDEN_SELECTOR_KEYS
    if forbidden_found:
        raise ValueError(
            f"금지된 selector 키 포함: {forbidden_found}. password/OTP/cert_password selector는 저장 불가."
        )
    _PACKS[site_id] = {"site_id": site_id, "selectors": selectors}


def validate_selector_pack(selectors: dict[str, list[str]]) -> list[str]:
    """selector pack 유효성 검사. 위반 목록 반환."""
    violations = []
    for key in selectors:
        if key in _FORBIDDEN_SELECTOR_KEYS:
            violations.append(f"금지 selector 키: {key}")
    return violations


def generate_skeleton_pack(site_id: str) -> dict[str, Any]:
    """신규 사이트 selector pack skeleton 생성."""
    return {
        "site_id": site_id,
        "selectors": {
            "login_required_markers": [],
            "publish_button_candidates": [],
            "save_draft_candidates": [],
            "title_input_candidates": [],
            "body_editor_candidates": [],
            "auth_signal_markers": [],
        },
        "_note": "password/OTP/cert_password selector는 추가 금지",
    }
