"""Generic Selector Discovery — known pack 없이 화면에서 selector 후보를 찾는다."""
from __future__ import annotations

from typing import Any

# 절대 건드리지 않을 selector 유형
_FORBIDDEN_DISCOVERY_TARGETS = frozenset([
    "password", "otp", "cert_password", "certificate_password",
    "npki", "credit_card", "captcha",
])

# 위험 버튼 — 발견만 하고 실행하지 않음
_RISK_BUTTON_KEYWORDS: list[tuple[str, str]] = [
    ("결제",       "payment"),
    ("pay",        "payment"),
    ("payment",    "payment"),
    ("전자서명",   "sign"),
    ("서명",       "sign"),
    ("e-sign",     "sign"),
    ("입찰",       "bid"),
    ("투찰",       "bid"),
    ("낙찰",       "bid"),
    ("송금",       "transfer"),
    ("이체",       "transfer"),
    ("계약 제출",  "legal_submit"),
    ("최종 제출",  "legal_submit"),
    ("삭제",       "delete"),
]

# AUTO 후보 selector 패턴
_SEARCH_BOX_CANDIDATES = [
    "input[type='search']", "input[placeholder*='검색']", "input[placeholder*='search']",
    "#search", ".search-input", "input[name='query']", "input[name='q']",
]
_LIST_ITEM_CANDIDATES = [
    "ul li a", "ol li a", ".list-item", ".board-item", "table tbody tr",
    ".article-item", ".post-item", ".notice-item",
]
_ARTICLE_LINK_CANDIDATES = [
    "a[href*='/view']", "a[href*='/post']", "a[href*='/article']",
    "a[href*='/notice']", ".title a", ".subject a",
]
_DOWNLOAD_LINK_CANDIDATES = [
    "a[href$='.pdf']", "a[href$='.xlsx']", "a[href$='.hwp']",
    "a[href$='.zip']", "a[href*='download']", "a[href*='attach']",
    ".attach a", ".file a",
]
_TITLE_INPUT_CANDIDATES = [
    "input[placeholder*='제목']", "input[name='title']",
    "input[placeholder*='title']", "#title", ".title-input",
]
_BODY_EDITOR_CANDIDATES = [
    "div[contenteditable='true']", "textarea", "#content",
    ".editor", ".ql-editor", "iframe.editor",
]
_SAVE_DRAFT_CANDIDATES = [
    "button:has-text('임시저장')", "button:has-text('draft')",
    "button[name='draft']", ".btn-draft",
]
_PREVIEW_CANDIDATES = [
    "button:has-text('미리보기')", "button:has-text('preview')",
    ".btn-preview",
]
_PUBLISH_CANDIDATES = [
    "button:has-text('발행')", "button:has-text('게시')",
    "button:has-text('publish')", ".btn-publish",
]
_SUBMIT_CANDIDATES = [
    "button[type='submit']", "input[type='submit']",
    "button:has-text('제출')", "button:has-text('신청')", ".btn-submit",
]
_DELETE_CANDIDATES = [
    "button:has-text('삭제')", "button:has-text('delete')", ".btn-delete",
]


def discover_selectors(observation: dict[str, Any]) -> dict[str, Any]:
    """
    page observation에서 selector 후보를 발견한다.
    실제 DOM 접근 없이 observation 기반으로 추정.

    반환:
      search_box: list[str]
      list_items: list[str]
      article_links: list[str]
      download_links: list[str]
      title_input: list[str]
      body_editor: list[str]
      save_draft_button: list[str]
      preview_button: list[str]
      publish_button: list[str]   # 발견만, 실행은 권한 gate 이후
      submit_button: list[str]    # 발견만
      delete_button: list[str]    # 발견만
      risk_buttons_detected: list[str]   # 위험 버튼 유형 목록
      password_selector_discovered: False
      otp_selector_discovered: False
    """
    buttons = [b.lower() for b in observation.get("buttons_observed", [])]
    visible_actions = observation.get("visible_actions", [])
    forms_detected = observation.get("forms_detected", False)

    # risk 버튼 감지 (발견만)
    risk_buttons_detected = []
    for btn_text in buttons:
        for kw, risk_type in _RISK_BUTTON_KEYWORDS:
            if kw.lower() in btn_text and risk_type not in risk_buttons_detected:
                risk_buttons_detected.append(risk_type)

    return {
        "search_box": _SEARCH_BOX_CANDIDATES if "search" in visible_actions else [],
        "list_items": _LIST_ITEM_CANDIDATES,
        "article_links": _ARTICLE_LINK_CANDIDATES,
        "download_links": _DOWNLOAD_LINK_CANDIDATES if "download" in visible_actions else [],
        "title_input": _TITLE_INPUT_CANDIDATES if forms_detected else [],
        "body_editor": _BODY_EDITOR_CANDIDATES if forms_detected else [],
        "save_draft_button": _SAVE_DRAFT_CANDIDATES if forms_detected else [],
        "preview_button": _PREVIEW_CANDIDATES if forms_detected else [],
        "publish_button": _PUBLISH_CANDIDATES if "publish" in visible_actions else [],
        "submit_button": _SUBMIT_CANDIDATES if ("submit" in visible_actions or forms_detected) else [],
        "delete_button": _DELETE_CANDIDATES if "delete" in visible_actions else [],
        "risk_buttons_detected": risk_buttons_detected,
        # 안전 경계 — 절대 False
        "password_selector_discovered": False,
        "otp_selector_discovered": False,
        "cert_password_selector_discovered": False,
        "npki_selector_discovered": False,
    }


def has_risk_buttons(discovered: dict[str, Any]) -> bool:
    return bool(discovered.get("risk_buttons_detected"))


def get_risk_button_types(discovered: dict[str, Any]) -> list[str]:
    return discovered.get("risk_buttons_detected", [])
