"""AI 기반 블로그 글 자동 작성 + 발행.

흐름:
  1. 주제/키워드 입력 → AI가 제목/본문/태그 자동 생성
  2. SEO 분석 자동 적용
  3. 이미지 자동 생성 (옵션)
  4. 임시저장 또는 예약 발행

요구: AIResponder + BlogWriter + BlogSEO
"""

from __future__ import annotations

from datetime import datetime, timedelta

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger
from scripts.naver.blog.seo.tag_suggester import (
    _COMPOUND_PAIRS,
    _STOPWORDS,
    suggest_tags,
)

_log = get_logger(__name__)

__all__ = ["_COMPOUND_PAIRS", "_STOPWORDS", "BlogAIWriter", "suggest_tags"]


class BlogAIWriter:
    """AI 글 작성 + 자동 발행."""

    def __init__(self, page: Page):
        self.page = page

    def draft(
        self,
        topic: str,
        keywords: list[str] | None = None,
        length: str = "medium",
        tone: str = "친근",
        return_seo: bool = True,
    ) -> dict:
        """AI로 글 초안 생성 + SEO 분석."""
        from scripts.naver.automation.integration.ai_responder import AIResponder

        ai = AIResponder()

        # 제목 생성
        title_r = ai._call(
            "한국 블로그 SEO 전문가입니다. 클릭 유도 + 검색 노출 좋은 제목 1개. 30~50자.",
            f"주제: {topic}\n키워드: {', '.join(keywords or [])}\n제목:",
            max_tokens=100,
        )
        title = title_r.get("text", topic).split("\n")[0].strip().strip('"').strip("'")

        # 본문 생성
        body_r = ai.draft_blog_post(topic, keywords=keywords, length=length)
        body = body_r.get("text", "")

        result = {"ok": title_r.get("ok") and body_r.get("ok"), "title": title, "body": body}

        # SEO 분석
        if return_seo and result["ok"]:
            from scripts.naver.blog.seo.seo import BlogSEO

            seo = BlogSEO(self.page)
            result["seo"] = seo.optimize_post(title, body, target_keywords=keywords)

        log_critical("OTHER", f"AI 블로그 초안: {title[:40]}", topic=topic, length=length, mode="blog_ai_draft")
        return result

    def draft_and_save(
        self,
        topic: str,
        keywords: list[str] | None = None,
        publish: bool = False,
        schedule_at: datetime | None = None,
        length: str = "medium",
        approval: str | None = None,
    ) -> dict:
        """초안 생성 → 임시저장 또는 발행/예약. publish=True 는 사용자가 직접 입력한 승인 문구(approval)가 필요하다."""
        if publish and not schedule_at:
            from scripts.common.gate import require_approved

            require_approved("blog_publish", approval, via="blog_ai_draft_and_save")
        draft = self.draft(topic, keywords=keywords, length=length, return_seo=False)
        if not draft.get("ok"):
            return draft

        from scripts.naver.blog.writer import BlogWriter

        bw = BlogWriter(self.page)
        if not bw.open():
            return {"ok": False, "error": "editor_open_failed", "draft": draft}

        bw.set_title(draft["title"])
        bw.write_body(draft["body"])
        if keywords:
            bw.set_tags(keywords[:7])

        if schedule_at:
            # 예약 발행은 BlogSchedule 모듈로 큐잉
            from scripts.naver.blog.schedule import BlogSchedule

            sch = BlogSchedule(self.page)
            r = sch.queue(schedule_at, draft["title"], draft["body"], tags=keywords, visibility="public")
            return {"ok": True, "mode": "scheduled", "draft": draft, "schedule": r}
        elif publish:
            r = bw.publish(wait_verify_s=8)
            return {"ok": r.get("ok"), "mode": "published", "draft": draft, "result": r}
        else:
            r = bw.save_draft()
            return {"ok": r.get("ok"), "mode": "draft_saved", "draft": draft, "result": r}

    def bulk_draft(self, topics: list[dict], publish_each: bool = False, delay_hours: int = 24) -> dict:
        """여러 주제 일괄 작성 + (옵션) 시간차 예약 발행.

        topics: [{"topic": "...", "keywords": [...]}, ...]
        delay_hours: 발행 간격 (예약 시)
        """
        results = []
        now = datetime.now()
        for i, t in enumerate(topics):
            schedule_at = now + timedelta(hours=delay_hours * i) if publish_each else None
            r = self.draft_and_save(
                t["topic"],
                keywords=t.get("keywords"),
                publish=False,
                schedule_at=schedule_at,
                length=t.get("length", "medium"),
            )
            results.append({"topic": t["topic"], "result": r})
        return {"ok": True, "count": len(results), "results": results}
