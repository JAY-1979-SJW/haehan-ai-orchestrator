"""네이버 블로그 기능 Mixin — 책임별 서브믹스인 aggregator.

BlogMixin 은 read/write/neighbor/collect/download/common 서브믹스인을 다중상속으로
결합한다. 각 기능 구현은 blog_mixin_<group>.py 에 있고, 메서드 간 호출은 인스턴스(self)/
MRO 로 해결된다. 공개 API(BlogMixin) 와 BrowserAgent 다중상속은 무변경.
[docs/module_separation_standard.md]
"""
from __future__ import annotations

from scripts.naver.agent_mixins.blog_mixin_read import BlogReadMixin
from scripts.naver.agent_mixins.blog_mixin_write import BlogWriteMixin
from scripts.naver.agent_mixins.blog_mixin_neighbor import BlogNeighborMixin
from scripts.naver.agent_mixins.blog_mixin_collect import BlogCollectMixin
from scripts.naver.agent_mixins.blog_mixin_download import BlogDownloadMixin
from scripts.naver.agent_mixins.blog_mixin_common import BlogCommonMixin


class BlogMixin(
    BlogReadMixin,
    BlogWriteMixin,
    BlogNeighborMixin,
    BlogCollectMixin,
    BlogDownloadMixin,
    BlogCommonMixin,
):
    """네이버 블로그 기능 Mixin (서브믹스인 결합)."""
