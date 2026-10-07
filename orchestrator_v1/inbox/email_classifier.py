"""
이메일 규칙 기반 분류기
AI 미사용 — 제목/본문/발신자 키워드 매칭으로 보수적 분류
확신이 낮으면 general + needs_review=True
"""
from __future__ import annotations

import re

# ── 분류 규칙 정의 ────────────────────────────────────────────────────────────
# 각 항목: (category, keywords, candidate_task_type)
# 매칭 순서가 우선순위. 더 구체적인 규칙을 앞에 둔다.

_CATEGORY_RULES: list[tuple[str, list[str], str]] = [
    # 입찰/조달 (가장 구체적)
    ("bidding", [
        "입찰", "낙찰", "공고", "나라장터", "조달청", "g2b", "입찰공고",
        "제안요청서", "rfp", "공사", "시공", "발주", "수주", "계약 공고",
        "견적 요청서", "사전규격", "업체 등록",
    ], "bid_review"),

    # 회계/재무
    ("accounting", [
        "청구", "세금계산서", "invoice", "정산", "지급", "입금", "출금",
        "영수증", "회계", "예산", "비용", "결제", "급여", "원천징수",
        "부가세", "소득세", "세무", "재무",
    ], "accounting_review"),

    # 영업/견적
    ("sales", [
        "견적", "제안서", "영업", "상담", "계약", "납품", "구매",
        "단가", "공급", "가격", "문의", "거래", "협력사", "협약",
        "계약서", "발주서", "주문",
    ], "quote_response"),

    # 개발 (운영보다 먼저 — github/git/pr 등 더 구체적)
    ("development", [
        "github", "git", "pull request", " pr ", "릴리즈", "배포",
        "개발", "코드", "api", "버그", "테스트", "qa", "기능 개선", "패치",
    ], "dev_review"),

    # 운영/장애
    ("operations", [
        "장애", "오류", "error", "fail", "서버", "이슈",
        "알림", "모니터링", "점검", "긴급", "down", "재시작",
        "시스템", "운영", "로그", "수정 요청", "문제 발생",
    ], "ops_check"),

    # 회의/일정
    ("meeting", [
        "회의", "미팅", "일정", "회의록", "agenda", "minutes",
        "zoom", "teams", "워크숍", "세미나", "컨퍼런스", "출장",
    ], "meeting_prep"),
]

_HIGH_PRIORITY_KEYWORDS: list[str] = [
    "긴급", "즉시", "오늘", "마감", "장애", "오류", "error", "fail",
    "중요", "urgent", "asap", "critical", "down", "문제 발생",
]

_LOW_PRIORITY_KEYWORDS: list[str] = [
    "뉴스레터", "newsletter", "공지", "안내", "소식", "광고",
    "이벤트", "프로모션", "구독", "정기",
]

# 뉴스레터/광고성 발신 도메인 패턴
_NEWSLETTER_SENDER_PATTERNS: list[str] = [
    r"noreply", r"no-reply", r"newsletter", r"stibee",
    r"mailchimp", r"campaign", r"marketing", r"info@",
]


def _normalize(text: str) -> str:
    return text.lower().strip()


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    norm = _normalize(text)
    return [kw for kw in keywords if kw in norm]


def _is_newsletter_sender(sender: str) -> bool:
    s = _normalize(sender)
    return any(re.search(p, s) for p in _NEWSLETTER_SENDER_PATTERNS)


def classify(item: dict) -> dict:
    """
    inbox item 1건을 분류해 분류 메타데이터를 반환.
    item: inbox_store.save_mail이 저장한 dict.
    반환: {category, priority, needs_review, candidate_task_type, classification_reason}
    """
    title: str = item.get("title", "") or ""
    body: str = item.get("body_raw", "") or ""
    sender: str = item.get("sender", "") or ""

    search_text = f"{title} {body[:500]}"  # 본문은 앞 500자만

    # ── 카테고리 판정 ─────────────────────────────────────────────
    matched_category = "general"
    matched_task_type: str | None = None
    matched_keywords: list[str] = []

    for category, keywords, task_type in _CATEGORY_RULES:
        hits = _match_keywords(search_text, keywords)
        if hits:
            matched_category = category
            matched_task_type = task_type
            matched_keywords = hits
            break

    # ── 우선순위 판정 ─────────────────────────────────────────────
    high_hits = _match_keywords(search_text, _HIGH_PRIORITY_KEYWORDS)
    low_hits = _match_keywords(search_text, _LOW_PRIORITY_KEYWORDS)
    is_newsletter = _is_newsletter_sender(sender)

    if high_hits:
        priority = "high"
    elif low_hits or is_newsletter:
        priority = "low"
    elif matched_category in {"operations", "sales", "bidding"}:
        priority = "medium"
    else:
        priority = "low"

    # ── needs_review 판정 ─────────────────────────────────────────
    # 카테고리 미확정(general)이거나 키워드가 1개 이하면 검토 필요
    needs_review = (
        matched_category == "general"
        or len(matched_keywords) <= 1
        or is_newsletter
    )

    # 뉴스레터/광고는 task 후보 불필요
    if is_newsletter or matched_category == "general":
        matched_task_type = None

    # ── classification_reason 생성 ────────────────────────────────
    parts = []
    if matched_keywords:
        parts.append(f"키워드={matched_keywords[:3]}")
    if is_newsletter:
        parts.append("발신자=뉴스레터패턴")
    if high_hits:
        parts.append(f"긴급키워드={high_hits[:2]}")
    reason = "; ".join(parts) if parts else "키워드 미매칭→general"

    return {
        "category": matched_category,
        "priority": priority,
        "needs_review": needs_review,
        "candidate_task_type": matched_task_type,
        "classification_reason": reason,
    }
