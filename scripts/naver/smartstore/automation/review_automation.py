"""리뷰 자동 답변 — 스토어 / 플레이스 / 블로그 통합.

기능:
  - 미답변 리뷰 자동 조회
  - 별점/키워드 기반 템플릿 자동 매칭
  - 자동 답변 작성 (★ confirm=True 시에만 발송)
"""

from __future__ import annotations

import re

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


DEFAULT_TEMPLATES = {
    "positive": "{author}님, 좋은 리뷰 감사합니다! 앞으로도 좋은 상품으로 보답하겠습니다.",
    "neutral": "{author}님, 리뷰 감사합니다. 더 나은 서비스로 보답하도록 노력하겠습니다.",
    "negative": "{author}님, 불편을 끼쳐 죄송합니다. 빠르게 개선하도록 하겠습니다.",
}


class ReviewAutoResponder:
    """리뷰 자동 답변 (스토어/플레이스/블로그 공통)."""

    def __init__(self, page: Page, templates: dict | None = None):
        self.page = page
        self.templates = templates or DEFAULT_TEMPLATES

    # ── 리뷰 분류 (별점/키워드 기반) ──────────────────────────────────

    def classify_review(self, review: dict) -> str:
        """positive / neutral / negative 분류."""
        rating = review.get("rating", "")
        content = (review.get("content", "") or "").lower()

        # 별점 우선 (1~5 또는 "★★★★☆")
        m = re.search(r"\d", rating)
        if m:
            r = int(m.group())
            if r >= 4:
                return "positive"
            if r <= 2:
                return "negative"
            return "neutral"

        # 키워드
        positive_kw = ["좋", "최고", "추천", "만족", "perfect", "good", "great"]
        negative_kw = ["나쁨", "실망", "불만", "환불", "bad", "worst", "poor"]
        if any(k in content for k in positive_kw):
            return "positive"
        if any(k in content for k in negative_kw):
            return "negative"
        return "neutral"

    # ── 자동 답변 (스토어) ────────────────────────────────────────────

    def respond_smartstore_reviews(self, limit: int = 20, confirm: bool = False) -> dict:
        """스마트스토어 리뷰 자동 답변."""
        from scripts.naver.smartstore import NaverSmartStore

        store = NaverSmartStore(self.page)
        r = store.list_reviews(limit=limit)
        if not r.get("ok"):
            return r

        headers = r.get("headers", [])
        rows = r.get("rows", [])
        replied = 0  # noqa: F841
        plans = []
        for row in rows:
            # row 데이터에서 리뷰 정보 추출 (헤더 기반)
            review = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
            category = self.classify_review(
                {
                    "rating": review.get("별점", review.get("평점", "")),
                    "content": review.get("리뷰내용", review.get("내용", "")),
                }
            )
            template = self.templates.get(category, "")
            author = review.get("작성자", review.get("회원", "고객"))
            response = template.format(author=author)
            plans.append({"author": author, "category": category, "response": response[:80]})

            if confirm:
                # 실제 답변 작성 (UI 구체화 필요)
                pass

        log_critical("OTHER", f"리뷰 자동 답변 {len(plans)}건 plan", dry_run=not confirm, mode="review_auto_respond")
        return {"ok": True, "dry_run": not confirm, "plans": plans, "total": len(rows)}

    # ── 자동 답변 (스마트플레이스) ────────────────────────────────────

    def respond_place_reviews(self, limit: int = 20, confirm: bool = False) -> dict:
        """스마트플레이스 리뷰 자동 답변."""
        from scripts.naver.common.place import NaverPlace

        place = NaverPlace(self.page)
        reviews = place.reviews(limit=limit)
        plans = []
        for rv in reviews:
            category = self.classify_review(rv)
            template = self.templates.get(category, "")
            response = template.format(author=rv.get("author", "고객"))
            plans.append({"author": rv.get("author", ""), "category": category, "response": response[:80]})
        return {"ok": True, "dry_run": not confirm, "plans": plans, "total": len(reviews)}
