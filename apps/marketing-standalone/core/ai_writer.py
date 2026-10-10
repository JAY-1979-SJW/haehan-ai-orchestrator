"""AI 블로그 초안 생성 — 독립 앱 전용 (원본: scripts/naver/blog/core/ai_writer.py).

원본과 차이:
  - Playwright Page 의존 제거 — SEO 분석은 페이지 없이 텍스트만으로 하는
    core.content_rules.seo_check 를 재사용(이미 이 앱에 있음).
  - core.ai_responder(이 앱 사본, 고객 본인 OpenAI 키) 사용.
"""

from __future__ import annotations

from core.ai_responder import AIResponder
from core.content_rules import seo_check


def draft(topic: str, keywords: list[str] | None = None, length: str = "medium") -> dict:
    """주제 → {title, body, seo} 초안 생성. 실패 시 ok=False."""
    ai = AIResponder()

    title_r = ai._call(
        "한국 블로그 SEO 전문가입니다. 클릭 유도 + 검색 노출 좋은 제목 1개. 30~50자.",
        f"주제: {topic}\n키워드: {', '.join(keywords or [])}\n제목:",
        max_tokens=100,
    )
    if not title_r.get("ok"):
        return {"ok": False, "error": title_r.get("error", "title_generation_failed")}
    title = title_r["text"].split("\n")[0].strip().strip('"').strip("'")

    body_r = ai.draft_blog_post(topic, keywords=keywords, length=length)
    if not body_r.get("ok"):
        return {"ok": False, "error": body_r.get("error", "body_generation_failed")}
    body = body_r["text"]

    seo = seo_check(title=title, body=body, keywords=keywords or [])
    return {"ok": True, "title": title, "body": body, "tags": (keywords or [])[:7], "seo": seo}
