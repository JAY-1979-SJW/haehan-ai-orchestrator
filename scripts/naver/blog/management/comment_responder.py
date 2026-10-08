"""블로그 댓글 자동 응답 — 모니터링 + AI/템플릿 답글.

기능:
  - 미응답 댓글 자동 조회
  - 분류 (질문/감사/비판/스팸)
  - 템플릿 또는 AI 자동 답글
  - 일괄 답글 (★ confirm 필수)
"""

from __future__ import annotations

import re
import time

from playwright.sync_api import Page

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


DEFAULT_TEMPLATES = {
    "thanks": "{author}님, 따뜻한 댓글 감사합니다!",
    "question": "{author}님, 좋은 질문이네요. 추가 안내드릴 수 있도록 확인해 보겠습니다.",
    "neutral": "{author}님, 댓글 남겨주셔서 감사합니다.",
    "spam": None,  # 답글 안 함
}


class BlogCommentResponder:
    """블로그 댓글 자동 응답."""

    def __init__(self, page: Page, blog_id: str, templates: dict | None = None, ai_enabled: bool = False):
        self.page = page
        self.blog_id = blog_id
        self.templates = templates or DEFAULT_TEMPLATES
        self.ai_enabled = ai_enabled

    def classify(self, comment_text: str) -> str:
        """댓글 분류."""
        text = comment_text.lower()
        if re.search(r"\?|어떻|왜|언제|얼마|how|what|why", text):
            return "question"
        if any(w in text for w in ["감사", "고마", "잘봤", "잘 봤", "좋아"]):
            return "thanks"
        if any(w in text for w in ["광고", "홍보", "방문해", "http"]):
            return "spam"
        return "neutral"

    def fetch_unreplied(self, post_url: str, limit: int = 20) -> list[dict]:
        """포스트의 미답글 댓글 추출."""
        self.page.goto(post_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)
        for f in self.page.frames:
            try:
                items = f.evaluate(
                    """
                (limit) => {
                    const out = [];
                    document.querySelectorAll('.u_cbox_comment, .CommentItem, [class*="comment"]').forEach((el, i) => {
                        if (i >= limit) return;
                        const author = el.querySelector('[class*="name"], [class*="nick"]')?.innerText?.trim() || '';
                        const text = el.querySelector('[class*="contents"], [class*="text"]')?.innerText?.trim() || '';
                        const date = el.querySelector('[class*="date"], [class*="time"]')?.innerText?.trim() || '';
                        // 이미 내가 답글했는지: 답글 영역에 내 닉네임 있는지
                        const replied = !!el.querySelector('[class*="reply"]');
                        if (text) out.push({author, text: text.substring(0, 200), date, replied});
                    });
                    return out;
                }
                """,
                    limit,
                )
                if items:
                    return [c for c in items if not c.get("replied")]
            except Exception:  # noqa: BLE001 - 댓글 목록 조회 실패시 다음 소스로 넘어가고, AI 답글 생성 실패시 템플릿 답글로 폴백 — 전송 여부와 무관한 읽기/생성 단계
                continue
        return []

    def auto_respond(self, post_url: str, send: bool = False, use_ai: bool | None = None) -> dict:
        """포스트의 미답글 댓글에 자동 답글 생성/발송."""
        use_ai = use_ai if use_ai is not None else self.ai_enabled
        unreplied = self.fetch_unreplied(post_url)
        if not unreplied:
            return {"ok": True, "count": 0}

        plans = []
        for c in unreplied:
            category = self.classify(c["text"])
            if category == "spam":
                continue
            # 답글 생성
            if use_ai:
                try:
                    from scripts.naver.automation.integration.ai_responder import (
                        AIResponder,
                    )

                    ai = AIResponder()
                    r = ai._call(
                        "당신은 블로그 운영자입니다. 댓글에 친절하게 답글 100자 이내로.",
                        f"댓글: {c['text']}\n작성자: {c['author']}\n답글:",
                        max_tokens=200,
                    )
                    reply = r.get("text", self.templates.get(category, "").format(author=c["author"]))
                except Exception:  # noqa: BLE001 - 댓글 목록 조회 실패시 다음 소스로 넘어가고, AI 답글 생성 실패시 템플릿 답글로 폴백 — 전송 여부와 무관한 읽기/생성 단계
                    reply = self.templates.get(category, "").format(author=c["author"])
            else:
                template = self.templates.get(category) or ""
                reply = template.format(author=c["author"]) if template else ""

            if reply:
                plans.append({"comment": c, "category": category, "reply": reply})

        if not send:
            return {"ok": True, "dry_run": True, "plans": plans}

        # 실제 답글 (UI 분석 후 구현)
        log_critical(
            "OTHER", f"댓글 자동 답글: {len(plans)}건", post=post_url, count=len(plans), mode="comment_auto_reply"
        )
        return {"ok": True, "plans": plans, "note": "실제 답글 UI는 댓글별 진입 + 답글 폼 클릭 필요"}
