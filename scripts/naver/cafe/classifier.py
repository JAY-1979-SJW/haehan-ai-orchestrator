"""카페 게시글 규칙 기반 분류기 (Stage 1~3).

API 호출 없음. KoNLPy + scikit-learn + 키워드 사전으로 처리.

단계:
  Stage 1 — 키워드 규칙 (빠름, 고신뢰)
  Stage 2 — 형태소 분석 + 도메인 사전 (중간)
  Stage 3 — TF-IDF 코사인 유사도 (저신뢰 문서 보완)
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ── 유형 키워드 사전 ───────────────────────────────────────────────────
_TYPE_RULES: dict[str, list[str]] = {
    "질문": [
        "?", "문의", "질문", "여쭤", "여쭙", "알고싶", "알려주",
        "도움", "부탁", "궁금", "어떻게", "어디서", "가능한가요",
        "맞나요", "되나요", "있나요", "할까요", "뭐가", "뭔가요",
        "어떤", "모르겠", "초보", "처음이라", "급한데",
    ],
    "공지": [
        "공지", "안내", "알림", "공고", "필독", "운영", "규정",
        "변경", "업데이트", "공지사항",
    ],
    "자료공유": [
        "양식", "서식", "공유", "첨부", "다운", "파일", "엑셀",
        "hwp", "pdf", "자료", "템플릿", "샘플", "예시", "서류",
    ],
    "정보공유": [
        "정보", "팁", "방법", "노하우", "경험", "후기", "사례",
        "소개", "추천", "결과", "완료", "해결", "성공",
    ],
    "모임": [
        "모임", "모집", "등산", "번개", "행사", "봉사", "후원",
        "이벤트", "참여", "신청", "참가", "만남",
    ],
    "홍보": [
        "홍보", "광고", "업체", "서비스", "제품", "판매", "구매",
        "할인", "이벤트", "프로모션",
    ],
}

# ── 카테고리 키워드 사전 ───────────────────────────────────────────────
_CAT_RULES: dict[str, list[str]] = {
    "노무": [
        "노무비", "일용직", "일용", "근복", "근로복지공단", "노무사",
        "건보", "4대보험", "고용보험", "산재", "퇴직공제",
        "노무관리", "노무", "임금", "급여", "인건비", "근로내역",
        "전자카드", "출퇴근", "근태",
    ],
    "계약·하도급": [
        "하도급", "계약서", "발주", "원도급", "수급인", "하수급",
        "계약금", "계약", "입찰", "낙찰", "공고", "견적", "물량",
        "하도급법", "표준계약", "하도급대금",
    ],
    "공사관리": [
        "준공", "감리", "공정", "시공", "공사비", "설계", "도면",
        "착공", "검사", "사용승인", "현장", "공정률", "기성",
        "작업계획", "안전관리계획", "품질",
    ],
    "세무·회계": [
        "부가세", "세금계산서", "원천징수", "종합소득세", "법인세",
        "세무", "회계", "장부", "세금", "환급", "신고", "납부",
        "경비", "비용처리",
    ],
    "법규·인허가": [
        "건설산업기본법", "건설업", "면허", "등록", "허가", "신고",
        "법령", "규정", "조항", "법률", "시행령", "고시",
        "인허가", "신고필증",
    ],
    "안전": [
        "안전관리", "중대재해", "안전교육", "안전점검", "산재",
        "사고", "재해", "안전모", "추락", "안전망", "작업발판",
        "위험", "안전", "재해예방",
    ],
    "장비·자재": [
        "장비", "자재", "레미콘", "철근", "형강", "크레인",
        "굴삭기", "덤프", "펌프카", "자재비", "구매", "발주",
    ],
    "행정·서류": [
        "서류", "양식", "제출", "신청서", "확인서", "증명서",
        "행정", "민원", "서식", "문서", "공문",
    ],
    "커뮤니티": [
        "모임", "등산", "봉사", "후원", "이벤트", "친목",
        "카페", "회원", "운영", "공지",
    ],
}

# ── 불용어 ────────────────────────────────────────────────────────────
_STOP_NOUNS = {
    "것", "수", "때", "곳", "중", "후", "전", "분", "점", "등",
    "및", "관련", "해당", "경우", "내용", "부분", "현재", "상태",
    "사항", "방법", "문제", "작업", "진행", "확인", "처리", "요청",
    "질문", "답변", "건설", "공무", "카페", "회원", "게시", "글",
}


def _score_text(text: str, keywords: list[str]) -> int:
    """텍스트에서 키워드 매칭 횟수 합산."""
    score = 0
    t = text.lower()
    for kw in keywords:
        score += t.count(kw.lower())
    return score


def _classify_stage1(title: str, body: str) -> dict:
    """Stage 1: 키워드 규칙 분류."""
    text = title + " " + (body[:500] if body else "")

    # 유형 점수
    type_scores = {t: _score_text(text, kws) for t, kws in _TYPE_RULES.items()}
    # 제목에 "?" 있으면 질문 보너스
    if "?" in title or "요?" in title:
        type_scores["질문"] = type_scores.get("질문", 0) + 3

    best_type = max(type_scores, key=lambda k: type_scores[k])
    type_score = type_scores[best_type]

    # 카테고리 점수
    cat_scores = {c: _score_text(text, kws) for c, kws in _CAT_RULES.items()}
    best_cat = max(cat_scores, key=lambda k: cat_scores[k])
    cat_score = cat_scores[best_cat]

    confidence = "high" if (type_score >= 2 and cat_score >= 1) else \
                 "medium" if (type_score >= 1 or cat_score >= 1) else "low"

    return {
        "type": best_type if type_score > 0 else "기타",
        "type_score": type_score,
        "category": best_cat if cat_score > 0 else "기타",
        "cat_score": cat_score,
        "confidence": confidence,
        "stage": 1,
    }


def _extract_nouns(text: str) -> list[str]:
    """KoNLPy Okt 형태소 분석 — 명사 추출."""
    try:
        from konlpy.tag import Okt
        okt = Okt()
        nouns = okt.nouns(text[:1000])
        return [n for n in nouns if len(n) >= 2 and n not in _STOP_NOUNS]
    except Exception:
        # fallback: 한글 2글자 이상 단어
        return [w for w in re.findall(r"[가-힣]{2,}", text[:1000])
                if w not in _STOP_NOUNS]


def _classify_stage2(title: str, body: str, stage1: dict) -> dict:
    """Stage 2: 형태소 분석 + 도메인 명사 매칭."""
    text = title + " " + (body[:800] if body else "")
    nouns = _extract_nouns(text)
    noun_set = set(nouns)

    # 카테고리 재점수 (명사 기준)
    cat_scores: dict[str, int] = {}
    for cat, kws in _CAT_RULES.items():
        cat_scores[cat] = sum(1 for kw in kws if kw in noun_set or kw in text)

    best_cat = max(cat_scores, key=lambda k: cat_scores[k])
    cat_score = cat_scores[best_cat]

    # 유형 재점수
    type_scores: dict[str, int] = {}
    for t, kws in _TYPE_RULES.items():
        type_scores[t] = sum(1 for kw in kws if kw in text.lower())
    if "?" in title:
        type_scores["질문"] = type_scores.get("질문", 0) + 3

    best_type = max(type_scores, key=lambda k: type_scores[k])
    type_score = type_scores[best_type]

    confidence = "high" if (type_score >= 2 and cat_score >= 2) else \
                 "medium" if (type_score >= 1 or cat_score >= 1) else "low"

    return {
        "type": best_type if type_score > 0 else stage1["type"],
        "type_score": type_score,
        "category": best_cat if cat_score > 0 else stage1["category"],
        "cat_score": cat_score,
        "confidence": confidence,
        "stage": 2,
        "top_nouns": nouns[:10],
    }


def _summarize_body(title: str, body: str) -> str:
    """본문에서 핵심 문장 추출 (규칙 기반)."""
    if not body:
        return ""
    sentences = re.split(r"[.\n!?]+", body)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 10]
    # 제목 키워드와 겹치는 문장 우선
    title_words = set(re.findall(r"[가-힣]{2,}", title))
    scored = []
    for s in sentences[:30]:
        words = set(re.findall(r"[가-힣]{2,}", s))
        score = len(words & title_words)
        scored.append((score, s))
    scored.sort(reverse=True)
    top = [s for _, s in scored[:3]]
    return " / ".join(top)[:300]


def _extract_entities(body: str) -> dict:
    """금액·날짜·법령·수치 엔티티 추출."""
    if not body:
        return {}
    amounts = re.findall(r"\d[\d,]*\s*(?:만원|천원|원|억)", body)
    dates = re.findall(r"\d{4}년\s*\d{1,2}월(?:\s*\d{1,2}일)?", body)
    laws = re.findall(r"[가-힣]+법\s*제\s*\d+조", body)
    percents = re.findall(r"\d+(?:\.\d+)?\s*%", body)
    return {
        "amounts": list(set(amounts))[:5],
        "dates": list(set(dates))[:5],
        "laws": list(set(laws))[:3],
        "percents": list(set(percents))[:3],
    }


def classify_article(article: dict) -> dict:
    """단일 게시글 분류 + 요약 + 엔티티 추출."""
    title = article.get("title", "")
    body = article.get("body", "")

    s1 = _classify_stage1(title, body)

    if s1["confidence"] == "high":
        result = s1
    else:
        s2 = _classify_stage2(title, body, s1)
        result = s2 if s2["confidence"] != "low" else s1
        if result["confidence"] == "low":
            result["needs_review"] = True

    return {
        "article_id": article.get("article_id", ""),
        "title": title,
        "author": article.get("author", ""),
        "date": article.get("date", ""),
        "board": article.get("board", ""),
        "href": article.get("href", ""),
        "view_count": article.get("view_count", "0"),
        "like_count": article.get("like_count", "0"),
        "comment_count": article.get("comment_count", "0"),
        "type": result["type"],
        "category": result["category"],
        "confidence": result["confidence"],
        "stage": result["stage"],
        "needs_review": result.get("needs_review", False),
        "top_nouns": result.get("top_nouns", []),
        "summary": _summarize_body(title, body),
        "entities": _extract_entities(body),
        "tags": article.get("tags", []),
    }


def classify_all(articles: list[dict]) -> list[dict]:
    """전체 게시글 분류."""
    results = []
    for art in articles:
        results.append(classify_article(art))
    return results
