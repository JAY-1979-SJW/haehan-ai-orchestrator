"""블로그 태그 자동 추출 — 순수 유틸리티 (writer→ai_writer 순환 제거 목적).

ai_writer.suggest_tags 와 동일 로직. writer.py 가 ai_writer 를 import 하지
않도록 분리. ai_writer.suggest_tags 는 보존되어 기존 호출자에 영향 없음.
"""

from __future__ import annotations

import re

from scripts.common.logger import get_logger

_log = get_logger(__name__)

_STOPWORDS = {
    "및",
    "등",
    "의",
    "을",
    "를",
    "이",
    "가",
    "은",
    "는",
    "에",
    "에서",
    "으로",
    "로",
    "와",
    "과",
    "도",
    "만",
    "까지",
    "부터",
    "하여",
    "하고",
    "합니다",
    "입니다",
    "있습니다",
    "합니다",
    "했습니다",
    "됩니다",
    "되어",
    "위해",
    "위한",
    "통해",
    "통한",
    "대한",
    "관한",
    "관련",
    "기반",
    "사용",
    "이번",
    "앞으로",
    "지속적으로",
    "자동으로",
    "직접",
    "전체",
    "모든",
    "각",
    "및",
    "또는",
    "그리고",
    "하지만",
    "그러나",
    "따라서",
    "그래서",
    "소개",
    "안녕하세요",
    "감사합니다",
    "주요",
    "기능",
    "방식",
    # 2026-08-17: 실제 태그 목록에서 발견된 의미 없는 고빈출 일반명사/어미
    # ("원문(20)", "판단(20)", "정리(20)", "반복(20)", "사람(21)", "문서(20)",
    # "현장(20)", "확인(21)", "조건(2)", "있을까" 등) — 설명형 본문에서
    # 자연스럽게 자주 나오지만 검색 태그로서는 무의미해 SEO만 오염시킴.
    "원문",
    "판단",
    "정리",
    "반복",
    "사람",
    "문서",
    "확인",
    "조건",
    "작업",
    "있을까",
    "않게",
    "이렇게",
    "어떻게",
    "무엇",
    "경우",
    "부분",
    "내용",
    "정도",
    "가능",
    "필요",
    "이유",
    "이것",
    "그것",
    "저것",
    "여기",
    "거기",
}

_COMPOUND_PAIRS = [
    ("네이버", "블로그"),
    ("블로그", "자동화"),
    ("AI", "자동화"),
    ("업무", "자동화"),
    ("네이버", "자동화"),
    ("파이썬", "자동화"),
    ("블로그", "작성"),
    ("자동", "글쓰기"),
    ("AI", "솔루션"),
]



_KO_SUFFIXES = (
    "으로써",
    "으로서",
    "이라는",
    "에서는",
    "에서도",
    "으로도",
    "으로는",
    "합니다",
    "했습니다",
    "입니다",
    "됩니다",
    "있습니다",
    "없습니다",
    "습니다",
    "ㅂ니다",
    "하여서",
    "하지만",
    "하지",
    "하여",
    "하고",
    "하는",
    "하며",
    "하면",
    "되어서",
    "되어",
    "되는",
    "되고",
    "되며",
    "있어요",
    "없어요",
    "해요",
    "해서",
    "해도",
    "하면서",
    "하면",
    "할수",
    "할 수",
    "입니다",
    "이에요",
    "예요",
    "했어요",
    "했는데",
    "했는지",
    "라는",
    "라도",
    "라고",
    "이라",
    "이며",
    "이고",
    "부터",
    "까지",
    "마다",
    "에서",
    "으로",
    "과의",
    "와의",
    "과를",
    "와를",
    "에도",
    "에는",
    "에서",
    "이를",
    "가를",
    "를",
    "을",
    "이",
    "가",
    "은",
    "는",
    "의",
    "에",
    "와",
    "과",
    "도",
    "만",
    "로",
    "해서",
    "해도",
    "해",
)


def _add_tag(tag: str, tags: list[str], seen: set[str], max_tags: int) -> None:
    t = tag.strip().replace(" ", "")
    if t and len(t) >= 2 and t not in seen and len(tags) < max_tags:
        seen.add(t)
        tags.append(t)


def _top_body_tokens(body_tokens: list[str], seen: set[str]) -> list[str]:
    freq: dict[str, int] = {}
    for t in body_tokens:
        if t not in seen:
            freq[t] = freq.get(t, 0) + 1
    return sorted(freq, key=lambda x: -freq[x])[:10]


def suggest_tags(title: str, body: str, brand_tags: list[str] | None = None, max_tags: int = 20) -> list[str]:
    brands = brand_tags or []
    tags: list[str] = []
    seen: set[str] = set()

    def _add(tag: str) -> None:
        _add_tag(tag, tags, seen, max_tags)

    for b in brands:
        _add(b)

    title_tokens = _tokenize(title)
    for t in title_tokens:
        _add(t)

    body_tokens = _tokenize(body)
    for t in _top_body_tokens(body_tokens, seen):
        _add(t)

    all_words = set(title_tokens) | set(body_tokens)
    for a, b in _COMPOUND_PAIRS:
        if a in all_words and b in all_words:
            _add(a + b)

    for i in range(len(title_tokens) - 1):
        compound = title_tokens[i] + title_tokens[i + 1]
        if len(compound) >= 4:
            _add(compound)

    _log.info("[suggest_tags] 태그 %d개 추출: %s", len(tags), tags)
    return tags


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w가-힣a-zA-Z0-9\s]", " ", text)
    raw_tokens = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]
    result = []
    for tok in raw_tokens:
        stripped = tok
        for suffix in _KO_SUFFIXES:
            if stripped.endswith(suffix) and len(stripped) - len(suffix) >= 2:
                stripped = stripped[: len(stripped) - len(suffix)]
                break
        if stripped and len(stripped) >= 2 and stripped not in _STOPWORDS:
            result.append(stripped)
    return result
