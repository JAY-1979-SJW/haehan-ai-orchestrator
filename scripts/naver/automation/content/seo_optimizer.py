"""SEO 최적화 — 상품명/태그/설명 자동 추천.

기능:
  - 네이버쇼핑 검색량 추정 (검색 결과 수)
  - 상품명 키워드 밀도 분석
  - 추천 키워드 자동 생성
  - 제목 길이/구조 최적화 (40자 권장)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from playwright.sync_api import Page

from scripts.common.logger import get_logger

_log = get_logger(__name__)


# 네이버 상품명 가이드: 브랜드 + 모델 + 상품유형 + 색상/사이즈 + 수량
NAVER_PRODUCT_NAME_GUIDE = [
    "브랜드/제조사 명시",
    "고유 모델명/시리즈 포함",
    "주요 키워드 1~3개 자연스럽게",
    "40~50자 권장 (최대 100자)",
    "중복/특수문자 자제",
    "수식어(특가, 무료배송) 자제",
]


class SEOOptimizer:
    """상품 SEO 자동 분석 + 최적화 추천."""

    def __init__(self, page: Page):
        self.page = page

    def analyze_product_name(self, name: str, brand: str | None = None, category: str | None = None) -> dict:
        """상품명 SEO 분석."""
        issues = []
        score = 100

        # 길이 검사
        length = len(name)
        if length < 20:
            issues.append(f"상품명 너무 짧음 ({length}자) — 30자 이상 권장")
            score -= 15
        elif length > 100:
            issues.append(f"상품명 너무 김 ({length}자) — 50자 이하 권장")
            score -= 20
        elif length > 50:
            score -= 5

        # 브랜드 포함
        if brand and brand.lower() not in name.lower():
            issues.append(f"브랜드 '{brand}' 미포함")
            score -= 15

        # 특수문자
        special_count = len(re.findall(r"[★☆♥♡!@#$%^&*]", name))
        if special_count > 0:
            issues.append(f"특수문자 {special_count}개 — 검색 노출 저하")
            score -= special_count * 5

        # 광고성 단어
        ad_words = ["특가", "최저가", "베스트", "신상품", "할인", "1등", "최고"]
        found_ads = [w for w in ad_words if w in name]
        if found_ads:
            issues.append(f"광고성 단어 {found_ads} — 페널티 가능")
            score -= len(found_ads) * 5

        # 키워드 중복
        words = re.findall(r"[가-힣A-Za-z0-9]+", name)
        word_count = Counter(words)
        duplicates = [w for w, c in word_count.items() if c > 1 and len(w) >= 2]
        if duplicates:
            issues.append(f"중복 키워드 {duplicates}")
            score -= len(duplicates) * 5

        return {
            "ok": True,
            "name": name,
            "length": length,
            "word_count": len(words),
            "score": max(0, score),
            "issues": issues,
            "guide": NAVER_PRODUCT_NAME_GUIDE,
        }

    def suggest_keywords(self, category: str, limit: int = 10) -> dict:
        """네이버쇼핑 카테고리 검색 → 자주 등장하는 키워드 추출."""
        url = f"https://search.shopping.naver.com/search/all?query={category}"
        try:
            self.page.goto(url, timeout=15000, wait_until="domcontentloaded")
            import time

            time.sleep(2)
            titles = self.page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('[class*="product_title"], [class*="title"] a').forEach(el => {
                    const t = (el.innerText || '').trim();
                    if (t && t.length > 5 && t.length < 200) out.push(t);
                });
                return out;
            }
            """)
            # 키워드 빈도 분석
            all_words: list[Any] = []
            for t in titles:
                words = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", t)
                all_words.extend(w for w in words if len(w) >= 2)
            counter = Counter(all_words)
            # 일반 단어 필터
            stopwords = {"상품", "신상", "정품", "당일", "발송", "무료", "배송", "할인", "특가"}
            keywords = [
                {"word": w, "count": c}
                for w, c in counter.most_common(limit * 3)
                if w not in stopwords and category not in w
            ][:limit]
            return {
                "ok": True,
                "category": category,
                "keywords": keywords,
                "sample_titles": titles[:10],
            }
        except Exception as e:  # noqa: BLE001 - 네이버 상품명 SEO 분석(analyze_product_name, 읽기전용) - 분석 실패 시 error 필드가 있는 dict를 반환할 뿐 데이터 변경 없음
            return {"ok": False, "error": str(e)[:80]}

    def optimize(self, product: dict) -> dict:
        """상품 정보 종합 SEO 최적화 추천."""
        name = product.get("name", "")
        analysis = self.analyze_product_name(name, brand=product.get("brand"), category=product.get("category"))

        suggestions = []
        if analysis["score"] < 70:
            suggestions.append("상품명 재작성 필요 (score < 70)")
        if not product.get("brand"):
            suggestions.append("브랜드 명시 권장")
        if not product.get("model_name"):
            suggestions.append("모델명 추가 권장 (구체성↑)")

        # 키워드 추천
        if product.get("category"):
            kw = self.suggest_keywords(product["category"], limit=5)
            if kw.get("ok"):
                suggestions.append(f"인기 키워드: {[k['word'] for k in kw['keywords']]}")

        return {
            "ok": True,
            "analysis": analysis,
            "suggestions": suggestions,
            "score": analysis["score"],
        }
