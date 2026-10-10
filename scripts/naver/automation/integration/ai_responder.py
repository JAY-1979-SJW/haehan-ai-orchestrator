"""AI 기반 자동 응답 — 앱 런타임 유료 AI 호출 없음(2026-09-24: GPT·Anthropic 경로 모두 제거, 사용자 승인).

기능(인터페이스 유지):
  - 리뷰 컨텍스트 기반 맞춤 답변 생성
  - 고객 문의 자동 답변
  - 상품 설명 자동 생성
  - 블로그 글 초안 자동 작성

모든 호출은 app_ai_disabled 를 돌려준다(호출자는 고정 안내·템플릿으로 폴백).
문구가 필요하면 Claude Code 가 MCP 로 직접 작성하는 것이 표준 경로다.
"""

from __future__ import annotations

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class AIResponder:
    """자동 응답 생성기 — 앱 안에서는 AI 를 부르지 않는다."""

    def __init__(self, provider: str = "none", model: str | None = None):
        self.provider = "none"  # 유료 AI 제공자 없음(인자는 호환용으로만 받음)
        self.model = model or "none"
        self.api_key = None
        self.endpoint = ""

    def _call(self, system: str, user: str, max_tokens: int = 500) -> dict:
        return {
            "ok": False,
            "error": "app_ai_disabled",
            "hint": "앱 런타임 AI 없음 — Claude Code가 직접 문구를 작성하세요.",
        }

    # ── 리뷰 답변 ──────────────────────────────────────────────────────

    def reply_to_review(self, review: dict, store_name: str = "저희 매장") -> dict:
        """리뷰 컨텍스트로 맞춤 답변 생성."""
        system = (
            "당신은 한국 스마트스토어 판매자의 친절한 고객 응대 전문가입니다. "
            "리뷰에 정중하게 맞춤 답변을 작성하세요. 100자 이내. 이모티콘 사용 최소."
        )
        user = f"""다음 리뷰에 답변해 주세요.

[리뷰 정보]
- 작성자: {review.get("author", "고객")}
- 별점: {review.get("rating", "")}
- 내용: {review.get("content", "")[:300]}

[가이드]
- 매장명: {store_name}
- 부정적이면 사과+개선 의지
- 긍정적이면 감사+재방문 유도
- 중립적이면 정중하게 응대
"""
        r = self._call(system, user, max_tokens=300)
        if r.get("ok"):
            log_critical(
                "OTHER",
                f"AI 리뷰 답변 생성: {review.get('author', '')[:20]}",
                author=review.get("author"),
                model=self.model,
                mode="ai_reply_review",
            )
        return r

    # ── 고객 문의 답변 ─────────────────────────────────────────────────

    def reply_to_inquiry(self, inquiry: dict, context: dict | None = None) -> dict:
        """문의 내용으로 답변 초안 생성."""
        context = context or {}
        system = "당신은 친절한 스마트스토어 고객 응대 담당자입니다. 정확하고 간결하게 답변하세요. 200자 이내."
        user = f"""고객 문의에 답변해 주세요.

[문의]
{inquiry.get("content", "")[:500]}

[배경 정보]
- 상품: {context.get("product", "")}
- 배송 정책: {context.get("delivery", "평일 오후 2시까지 주문 당일 발송")}
- 교환/반품: {context.get("return_policy", "수령 후 7일 이내 가능")}
"""
        return self._call(system, user, max_tokens=400)

    # ── 상품 설명 생성 ─────────────────────────────────────────────────

    def generate_product_description(self, product: dict) -> dict:
        """상품 정보로 상세설명 자동 작성."""
        system = (
            "당신은 한국 스마트스토어 상품 카피라이터입니다. "
            "구매를 유도하는 매력적이고 명확한 상품 설명을 작성하세요. "
            "SEO 키워드 자연스럽게 포함. 500자 내외."
        )
        user = f"""상품 상세설명을 작성해 주세요.

상품명: {product.get("name", "")}
카테고리: {product.get("category", "")}
브랜드: {product.get("brand", "")}
모델: {product.get("model_name", "")}
주요 특징: {product.get("features", "미제공")}
타겟 고객: {product.get("target", "일반 소비자")}
"""
        return self._call(system, user, max_tokens=800)

    # ── 블로그 글 초안 ────────────────────────────────────────────────

    def draft_blog_post(self, topic: str, keywords: list[str] | None = None, length: str = "medium") -> dict:
        """블로그 글 초안 생성."""
        length_map = {"short": 500, "medium": 1500, "long": 3000}
        max_tok = length_map.get(length, 1500)
        kw_str = ", ".join(keywords or [])
        system = "한국어 블로그 작가입니다. SEO를 고려한 자연스러운 글을 작성하세요."
        user = f"주제: {topic}\n키워드: {kw_str}\n길이: {length}\n\n블로그 글을 작성해 주세요."
        return self._call(system, user, max_tokens=max_tok)
