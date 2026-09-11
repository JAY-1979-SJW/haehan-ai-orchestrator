"""게시글 제목 → 키워드 규칙 기반 카테고리 분류 (GPT 없음, 무료).

2026-09-12: "키워드로 분류" 요청 — AI 호출 없이 사전 정의한 키워드 사전으로
제목을 분류한다. 커뮤니티마다 카테고리 사전을 따로 두면 재사용 가능.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# 카테고리: [매칭 키워드]. 먼저 매칭되는 카테고리로 분류(순서 중요).
DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "야구_직캠_하이라이트": ["mp4", "직캠", "홈런", "적시타", "안타", ".gif"],
    "야구_이적_계약": ["계약", "연봉", "이적", "트레이드", "FA", "영입", "방출"],
    "야구_경기반응": ["승", "패", "경기", "선발", "불펜", "타율", "방어율", "kbo", "KBO"],
    "정치_사회": ["정치", "대통령", "국회", "정부", "법안", "시위"],
    "연예_아이돌": ["아이돌", "배우", "가수", "연예인", "드라마", "근황"],
    "유머_짤방": [".jpg", "ㅋㅋ", "asmr", "짤", "레전드"],
    "사건사고": ["사고", "화재", "사망", "부상", "경찰", "신고"],
    "잡담_일상": ["오늘", "점심", "저녁", "날씨", "출근", "퇴근"],
}


def classify_title(title: str, categories: dict[str, list[str]] | None = None) -> str:
    cats = categories or DEFAULT_CATEGORIES
    t = (title or "").lower()
    for name, keywords in cats.items():
        for kw in keywords:
            if kw.lower() in t:
                return name
    return "기타"


def classify_posts(posts: list[dict[str, Any]], categories: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """게시글 목록 → 카테고리별 집계 + 카테고리 태그가 붙은 게시글 목록."""
    tagged = []
    for p in posts:
        cat = classify_title(p.get("title", ""), categories)
        tagged.append({**p, "category": cat})

    counts = Counter(p["category"] for p in tagged)
    total = len(tagged) or 1
    breakdown = [
        {"category": name, "count": cnt, "share": round(cnt / total * 100, 1)} for name, cnt in counts.most_common()
    ]

    return {
        "ok": True,
        "total": len(tagged),
        "breakdown": breakdown,
        "posts": tagged,
    }
