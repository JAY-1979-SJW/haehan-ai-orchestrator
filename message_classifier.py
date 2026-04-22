"""
범용 메시지 분류기 — source_type 지원
email_classifier의 분류 로직을 최대한 재사용.
source_type별 보수적 보정 적용.
AI 미사용 — 규칙 기반.
"""
from __future__ import annotations

import re
from typing import Optional

from email_classifier import (
    _CATEGORY_RULES,
    _HIGH_PRIORITY_KEYWORDS,
    _LOW_PRIORITY_KEYWORDS,
    _match_keywords,
    _normalize,
    classify as _classify_email,
)

# ── 카카오 채널 전용 추가 규칙 ────────────────────────────────────────────────
# support 카테고리: 고객 문의/CS 성격 메시지 (카카오톡 채널에서 자주 발생)
# email_classifier의 _CATEGORY_RULES 앞에 prepend해서 우선 매칭

_KAKAO_PREFIX_RULES: list[tuple[str, list[str], str]] = [
    ("support", [
        "문의", "질문", "도움", "help", "support", "cs", "고객센터",
        "불편", "불만", "민원", "접수", "처리", "안내 요청",
        "어떻게", "언제", "얼마", "왜", "확인 부탁", "답변",
    ], "support_ticket"),
]

# 카카오 채널 메시지는 짧고 단어가 적어 확신 임계값을 높임
_KAKAO_MIN_KEYWORDS_FOR_CONFIDENT = 2


def _classify_kakao(item: dict, source_type: str) -> dict:
    """
    카카오워크/카카오톡채널 메시지 분류.
    support 카테고리 규칙을 우선 적용 후 email_classifier 규칙 사용.
    짧은 메시지 특성상 needs_review 임계값을 보수적으로 적용.
    """
    title: str = item.get("title", "") or ""
    body: str = item.get("body_raw", "") or ""
    sender: str = item.get("sender", "") or ""

    search_text = f"{title} {body[:300]}"  # 카카오 메시지는 짧으므로 300자

    # ── 카테고리 판정: 카카오 전용 규칙 우선 ─────────────────────────────────
    matched_category = "general"
    matched_task_type: Optional[str] = None
    matched_keywords: list[str] = []

    combined_rules = _KAKAO_PREFIX_RULES + list(_CATEGORY_RULES)
    for category, keywords, task_type in combined_rules:
        hits = _match_keywords(search_text, keywords)
        if hits:
            matched_category = category
            matched_task_type = task_type
            matched_keywords = hits
            break

    # ── 우선순위 판정 ─────────────────────────────────────────────────────────
    high_hits = _match_keywords(search_text, _HIGH_PRIORITY_KEYWORDS)
    low_hits = _match_keywords(search_text, _LOW_PRIORITY_KEYWORDS)

    if high_hits:
        priority = "high"
    elif low_hits:
        priority = "low"
    elif matched_category in {"operations", "sales", "bidding", "support"}:
        priority = "medium"
    else:
        priority = "low"

    # ── needs_review 판정 (카카오는 더 보수적) ────────────────────────────────
    # 메시지가 짧아 분류 확신이 낮으므로 키워드 2개 미만이면 검토 필요
    needs_review = (
        matched_category == "general"
        or len(matched_keywords) < _KAKAO_MIN_KEYWORDS_FOR_CONFIDENT
    )

    # general이면 task 후보 불필요
    if matched_category == "general":
        matched_task_type = None

    # ── classification_reason ─────────────────────────────────────────────────
    parts = [f"source={source_type}"]
    if matched_keywords:
        parts.append(f"키워드={matched_keywords[:3]}")
    if high_hits:
        parts.append(f"긴급키워드={high_hits[:2]}")
    if matched_category == "general":
        parts.append("키워드 미매칭→general")
    reason = "; ".join(parts)

    return {
        "category": matched_category,
        "priority": priority,
        "needs_review": needs_review,
        "candidate_task_type": matched_task_type,
        "classification_reason": reason,
    }


def classify_message(item: dict) -> dict:
    """
    source_type에 따라 분류 방식을 선택.
    email → 기존 email_classifier.classify() 그대로
    kakaowork / kakaotalk_channel → _classify_kakao()
    그 외 → email_classifier fallback
    """
    source_type = item.get("source_type", "email")

    if source_type == "email":
        return _classify_email(item)
    elif source_type in {"kakaowork", "kakaotalk_channel"}:
        return _classify_kakao(item, source_type)
    else:
        return _classify_email(item)
