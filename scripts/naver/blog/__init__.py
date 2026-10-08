"""블로그 통합 패키지 (고도화).

기존 scripts/naver/blog.py / blog_writer.py 위에 구축.

신규 모듈:
  - blog_series       : 시리즈 관리
  - blog_schedule     : 예약 발행
  - blog_seo          : SEO 최적화
  - blog_comment_responder : 댓글 자동 응답
  - blog_neighbor_manager  : 이웃 자동 관리
  - blog_analytics    : 방문/댓글 통계
  - blog_ai_writer    : AI 기반 글 자동 작성 + 발행

통합 진입점:
  from scripts.naver.blog import Blog
  b = Blog(page)
  b.writer.write_post(...)
  b.series.add_post(...)
  b.schedule.publish_at(...)
  b.seo.optimize(...)
  b.comments.auto_reply(...)
  b.neighbors.add_active_neighbors(...)
  b.analytics.daily_summary()
  b.ai.draft_and_publish(...)
"""
from __future__ import annotations

from playwright.sync_api import Page

from scripts.naver.blog.accounts import DEFAULT_ACCOUNT


class Blog:
    """블로그 통합 진입점."""

    def __init__(self, page: Page, blog_id: str = DEFAULT_ACCOUNT):
        self.page = page
        self.blog_id = blog_id
        self._writer = None
        self._writer_pro = None
        self._series = None
        self._schedule = None
        self._seo = None
        self._comments = None
        self._neighbors = None
        self._analytics = None
        self._ai = None

    @property
    def writer(self):
        if self._writer is None:
            from scripts.naver.blog.writer import BlogWriter
            self._writer = BlogWriter(self.page)
        return self._writer

    @property
    def writer_pro(self):
        """고도화 작성기: SEO+AI+템플릿+백업 통합."""
        if self._writer_pro is None:
            from scripts.naver.blog.writer_pro import BlogWriterPro
            self._writer_pro = BlogWriterPro(self.page, self.blog_id)
        return self._writer_pro

    @property
    def series(self):
        if self._series is None:
            from scripts.naver.blog.series import BlogSeries
            self._series = BlogSeries(self.page, self.blog_id)
        return self._series

    @property
    def schedule(self):
        if self._schedule is None:
            from scripts.naver.blog.schedule import BlogSchedule
            self._schedule = BlogSchedule(self.page)
        return self._schedule

    @property
    def seo(self):
        if self._seo is None:
            from scripts.naver.blog.seo.seo import BlogSEO
            self._seo = BlogSEO(self.page)
        return self._seo

    @property
    def comments(self):
        if self._comments is None:
            from scripts.naver.blog.comment_responder import BlogCommentResponder
            self._comments = BlogCommentResponder(self.page, self.blog_id)
        return self._comments

    @property
    def neighbors(self):
        if self._neighbors is None:
            from scripts.naver.blog.neighbor_manager import BlogNeighborManager
            self._neighbors = BlogNeighborManager(self.page, self.blog_id)
        return self._neighbors

    @property
    def analytics(self):
        if self._analytics is None:
            from scripts.naver.blog.analytics import BlogAnalytics
            self._analytics = BlogAnalytics(self.page, self.blog_id)
        return self._analytics

    @property
    def ai(self):
        if self._ai is None:
            from scripts.naver.blog.ai_writer import BlogAIWriter
            self._ai = BlogAIWriter(self.page)
        return self._ai


__all__ = ["Blog", "run"]

from ._runner import run  # CLI 진입점 (router용)

# 엔진 쪽 블로그 믹스인(L4)은 사이트 모듈(셀렉터·글쓰기, L5)을 import 하지 않는다 — 사이트 패키지가 로드될 때 여기서 넣어 준다(T4 주입)
from scripts.naver.blog import page_selectors as _selectors  # noqa: E402
from scripts.naver.agent_mixins.blog_mixin_write import BlogWriteMixin as _BlogWriteMixin  # noqa: E402
from scripts.naver.blog.core import writer as _writer  # noqa: E402

_BlogWriteMixin.configure_blog_write(selectors=_selectors, writer=_writer)
